using System;
using System.Data;
using System.IO;
using System.Linq;
using System.Net;
using Newtonsoft.Json;
using Syncfusion.DocIO;
using Syncfusion.DocIO.DLS;
using Syncfusion.DocIORenderer;
using Syncfusion.Pdf;
using Syncfusion.XlsIO;
using WDocument = Syncfusion.DocIO.DLS.WordDocument;
using WFormatType = Syncfusion.DocIO.FormatType;
using EJFormatType = Syncfusion.EJ2.DocumentEditor.FormatType;
using EJWordDocument = Syncfusion.EJ2.DocumentEditor.WordDocument;

namespace WebServiceLibrary
{
    /// <summary>
    /// Python-friendly wrapper for the Syncfusion EJ2 DocumentEditor
    /// service. Mirrors the original ASP.NET Core DocumentEditorController
    /// endpoints (Import, ImportFileURL, Export, Save, RestrictEditing,
    /// MailMerge) and exposes them as plain .NET methods callable from
    /// Python via pythonnet.
    ///
    /// The intent is that the same C# code is used both in the legacy
    /// ASP.NET Core service and in the Python wrapper — the Python Flask
    /// layer is responsible for HTTP plumbing (status codes, response
    /// bodies, file streaming) and just calls into this class.
    /// </summary>
    public class DocumentEditor
    {
        // ---- Security: filename + extension whitelist ----
        // Mirrors the constants used by the original controller.
        private static readonly string[] AllowedExtensions = new[]
        {
            ".docx", ".doc", ".rtf", ".txt", ".xml", ".html",
            ".dotx", ".docm", ".dotm", ".odt",
        };

        private static readonly char[] InvalidFileNameChars =
            Path.GetInvalidFileNameChars();

        public static bool IsAllowedExtension(string fileName)
        {
            if (string.IsNullOrEmpty(fileName)) return false;
            string ext = Path.GetExtension(fileName).ToLowerInvariant();
            return AllowedExtensions.Contains(ext);
        }

        public static bool IsValidFileName(string fileName)
        {
            if (string.IsNullOrEmpty(fileName)) return false;
            if (fileName.Contains("..") || fileName.Contains("/") || fileName.Contains("\\"))
                return false;
            return !InvalidFileNameChars.Any(c => fileName.Contains(c));
        }

        // ------------------------------------------------------------
        // Import — multipart/form-data with a single "file" field.
        // Loads the uploaded bytes, converts to SFDT JSON, returns the
        // JSON string. Same contract as the original
        // DocumentEditorController.Import.
        // ------------------------------------------------------------
        public string ImportFromBytes(byte[] bytes, string fileName)
        {
            if (bytes == null || bytes.Length == 0)
                throw new ArgumentException("File bytes are required.", nameof(bytes));
            if (string.IsNullOrEmpty(fileName))
                fileName = "Document.docx";

            int index = fileName.LastIndexOf('.');
            string type = (index > -1 && index < fileName.Length - 1)
                ? fileName.Substring(index)
                : ".docx";

            EJFormatType formatType = ParseEJFormatType(type.ToLowerInvariant());

            using (MemoryStream stream = new MemoryStream(bytes))
            {
                EJWordDocument document = EJWordDocument.Load(stream, formatType);
                string json = JsonConvert.SerializeObject(document);
                document.Dispose();
                return json;
            }
        }

        // ------------------------------------------------------------
        // ImportFileURL — fetch a .docx from a URL, then:
        //   1) Use DocIO MailMerge.GetMergeFieldNames() to extract the
        //      MERGEFIELD names actually referenced in the document.
        //   2) Load the same bytes as an EJ2 WordDocument and serialize
        //      to SFDT JSON.
        // Returns a 2-element object array: [sfdt, string[] mergeFields].
        // (Pythonnet doesn't unpack C# ValueTuples cleanly, so the
        // wrapper exposes a flat object[] which Python can read with
        // result[0] / result[1].)
        // ------------------------------------------------------------
        public object[] ImportFromFileUrl(string fileUrl)
        {
            if (string.IsNullOrWhiteSpace(fileUrl))
                throw new ArgumentException("fileUrl is required.", nameof(fileUrl));

            using (WebClient client = new WebClient())
            {
                byte[] downloaded = client.DownloadData(fileUrl);

                // 1) DocIO pass — get MERGEFIELD names.
                WDocument docxDoc = new WDocument(
                    new MemoryStream(downloaded), WFormatType.Docx);
                string[] mergeFieldNames = docxDoc.MailMerge.GetMergeFieldNames()
                                              ?? new string[0];
                docxDoc.Close();

                // 2) EJ2 pass — SFDT JSON.
                EJWordDocument document = EJWordDocument.Load(
                    new MemoryStream(downloaded), EJFormatType.Docx);
                string json = JsonConvert.SerializeObject(document);
                document.Dispose();
                return new object[] { json, mergeFieldNames };
            }
        }

        // ------------------------------------------------------------
        // RestrictEditing — hash (passwordBase64, saltBase64, spinCount)
        // for document protection. Returns the computed hash string[]
        // from WordDocument.ComputeHash (matches the original contract).
        // ------------------------------------------------------------
        public string[] RestrictEditing(string passwordBase64, string saltBase64, int spinCount)
        {
            if (string.IsNullOrEmpty(passwordBase64))
                return null;
            return EJWordDocument.ComputeHash(passwordBase64, saltBase64, spinCount);
        }

        // ------------------------------------------------------------
        // Save — persist SFDT to disk as the requested .docx file.
        // Replaces existing file at the same path (FileMode.Create).
        // ------------------------------------------------------------
        public void SaveToFile(string content, string fileName, string format, string templatesFolder)
        {
            if (string.IsNullOrEmpty(content))
                throw new ArgumentException("content (SFDT) is required.");
            if (string.IsNullOrEmpty(fileName))
                fileName = "Document" + ResolveFormatSuffix(format, fileName);

            string fmt = ResolveFormatSuffix(format, fileName);
            string safeName = fileName.EndsWith(fmt, StringComparison.OrdinalIgnoreCase)
                ? fileName
                : fileName + fmt;

            if (!IsValidFileName(safeName))
                throw new ArgumentException("Invalid filename format.");

            string savePath = Path.Combine(templatesFolder, Path.GetFileName(safeName));
            string fullPath = Path.GetFullPath(savePath);
            string allowedPath = Path.GetFullPath(templatesFolder);
            if (!fullPath.StartsWith(allowedPath, StringComparison.OrdinalIgnoreCase))
                throw new UnauthorizedAccessException(
                    "Access denied: Cannot save file outside allowed directory.");

            WDocument document = EJWordDocument.Save(content);
            try
            {
                using (FileStream fs = new FileStream(
                    savePath, FileMode.Create, FileAccess.ReadWrite))
                {
                    document.Save(fs, ParseWFormatType(fmt));
                }
            }
            finally
            {
                document.Close();
            }
        }

        // ------------------------------------------------------------
        // Export — serialize SFDT to a target format (Docx, Pdf, Rtf,
        // Html, Txt, etc.) and return the resulting bytes. The Python
        // layer streams them back to the client as an attachment.
        // Returns a 3-element object[]: [byte[] bytes, string contentType,
        // string fileName] (Pythonnet doesn't unpack C# ValueTuples).
        // ------------------------------------------------------------
        public object[] Export(
            string content, string fileName, string format)
        {
            if (string.IsNullOrEmpty(fileName)) fileName = "Document1.docx";
            string fmt = ResolveFormatSuffix(
                string.IsNullOrEmpty(format) ? fileName : format,
                fileName);
            if (!IsValidFileName(fileName))
                throw new ArgumentException("Invalid filename format.");

            WDocument document;
            if (string.Equals(fmt, ".pdf", StringComparison.OrdinalIgnoreCase))
            {
                using (Stream stream = EJWordDocument.Save(content, EJFormatType.Docx))
                {
                    document = new WDocument(stream, WFormatType.Docx);
                }
            }
            else
            {
                document = EJWordDocument.Save(content);
            }

            try
            {
                using (MemoryStream output = new MemoryStream())
                {
                    string contentType;
                    if (string.Equals(fmt, ".pdf", StringComparison.OrdinalIgnoreCase))
                    {
                        contentType = "application/pdf";
                        using (DocIORenderer renderer = new DocIORenderer())
                        using (PdfDocument pdf = renderer.ConvertToPDF(document))
                        {
                            pdf.Save(output);
                            pdf.Close();
                        }
                    }
                    else
                    {
                        WFormatType type = ParseWFormatType(fmt);
                        contentType = ContentTypeForWFormat(type);
                        document.Save(output, type);
                    }
                    return new object[] { output.ToArray(), contentType, fileName };
                }
            }
            finally
            {
                document.Close();
            }
        }

        // ------------------------------------------------------------
        // MailMerge — same logic as the original controller:
        //   * Decode the base64 .docx payload.
        //   * If mailMergeData is empty, fall back to the bundled
        //     Excel file at <filesRoot>/Data/CRE_Appraisal_POC.xlsx.
        //   * Execute MailMerge, return the merged SFDT JSON.
        // ------------------------------------------------------------
        public string MailMerge(
            string base64Document,
            string mailMergeDataJson,
            string filesRoot)
        {
            if (string.IsNullOrEmpty(base64Document))
                throw new ArgumentException("documentData cannot be null or empty.");

            string cleanBase64 = base64Document.Contains(',')
                ? base64Document.Split(',')[1]
                : base64Document;
            byte[] data = Convert.FromBase64String(cleanBase64);

            using (MemoryStream stream = new MemoryStream())
            {
                stream.Write(data, 0, data.Length);
                stream.Position = 0;

                using (WDocument document = new WDocument(
                    new MemoryStream(data), WFormatType.Docx))
                {
                    document.MailMerge.RemoveEmptyGroup = true;
                    document.MailMerge.RemoveEmptyParagraphs = true;
                    document.MailMerge.ClearFields = true;

                    if (string.IsNullOrWhiteSpace(mailMergeDataJson))
                    {
                        string excelPath = Path.Combine(
                            filesRoot, "Data", "CRE_Appraisal_POC.xlsx");
                        if (!File.Exists(excelPath))
                            throw new FileNotFoundException(
                                $"Merge-data Excel file not found: {excelPath}");

                        using (ExcelEngine excelEngine = new ExcelEngine())
                        {
                            excelEngine.Excel.DefaultVersion = ExcelVersion.Xlsx;
                            // IWorkbook doesn't implement IDisposable in
                            // this package; call Close() explicitly.
                            IWorkbook workbook =
                                excelEngine.Excel.Workbooks.Open(excelPath);
                            try
                            {
                                DataTable mergeTable = BuildMergeTable(workbook.Worksheets[0]);
                                if (mergeTable.Rows.Count > 0)
                                    document.MailMerge.Execute(mergeTable);
                            }
                            finally
                            {
                                workbook.Close();
                            }
                        }
                    }
                    else
                    {
                        DataTable mergeTable = JsonConvert.DeserializeObject<DataTable>(
                            mailMergeDataJson);
                        document.MailMerge.Execute(mergeTable);
                    }

                    document.Save(stream, WFormatType.Docx);
                }

                stream.Position = 0;
                EJWordDocument wordDocument = EJWordDocument.Load(
                    stream, EJFormatType.Docx);
                string sfdt = JsonConvert.SerializeObject(wordDocument);
                wordDocument?.Dispose();
                return sfdt;
            }
        }

        // ============================================================
        // Helpers
        // ============================================================

        private static DataTable BuildMergeTable(IWorksheet worksheet)
        {
            DataTable dataTable = worksheet.ExportDataTable(
                worksheet.UsedRange,
                ExcelExportDataTableOptions.ColumnNames);

            // Drop blank rows.
            for (int i = dataTable.Rows.Count - 1; i >= 0; i--)
            {
                bool isEmpty = true;
                foreach (DataColumn col in dataTable.Columns)
                {
                    if (!string.IsNullOrWhiteSpace(
                        dataTable.Rows[i][col]?.ToString()))
                    {
                        isEmpty = false;
                        break;
                    }
                }
                if (isEmpty) dataTable.Rows.RemoveAt(i);
            }
            return dataTable;
        }

        private static string ResolveFormatSuffix(string format, string fileName)
        {
            if (!string.IsNullOrWhiteSpace(format))
                return format.StartsWith(".") ? format : "." + format;

            if (string.IsNullOrEmpty(fileName)) return ".docx";
            int idx = fileName.LastIndexOf('.');
            if (idx > -1 && idx < fileName.Length - 1)
                return fileName.Substring(idx);
            return ".docx";
        }

        internal static EJFormatType ParseEJFormatType(string format)
        {
            switch ((format ?? string.Empty).ToLowerInvariant())
            {
                case ".dotx":
                case ".docx":
                case ".docm":
                case ".dotm":
                    return EJFormatType.Docx;
                case ".dot":
                case ".doc":
                    return EJFormatType.Doc;
                case ".rtf":
                    return EJFormatType.Rtf;
                case ".txt":
                    return EJFormatType.Txt;
                case ".xml":
                    return EJFormatType.WordML;
                case ".html":
                    return EJFormatType.Html;
                default:
                    throw new NotSupportedException(
                        "EJ2 DocumentEditor does not support this file format: " + format);
            }
        }

        internal static WFormatType ParseWFormatType(string format)
        {
            switch ((format ?? string.Empty).ToLowerInvariant())
            {
                case ".dotx": return WFormatType.Dotx;
                case ".docx": return WFormatType.Docx;
                case ".docm": return WFormatType.Docm;
                case ".dotm": return WFormatType.Dotm;
                case ".dot":  return WFormatType.Dot;
                case ".doc":  return WFormatType.Doc;
                case ".rtf":  return WFormatType.Rtf;
                case ".html": return WFormatType.Html;
                case ".txt":  return WFormatType.Txt;
                case ".xml":  return WFormatType.WordML;
                case ".odt":  return WFormatType.Odt;
                default:
                    throw new NotSupportedException(
                        "EJ2 DocumentEditor does not support this file format: " + format);
            }
        }

        private static string ContentTypeForWFormat(WFormatType type)
        {
            switch (type)
            {
                case WFormatType.Rtf:     return "application/rtf";
                case WFormatType.WordML:  return "application/xml";
                case WFormatType.Html:    return "application/html";
                case WFormatType.Dotx:    return "application/vnd.openxmlformats-officedocument.wordprocessingml.template";
                case WFormatType.Docx:    return "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
                case WFormatType.Doc:     return "application/msword";
                case WFormatType.Dot:     return "application/msword";
                case WFormatType.Odt:     return "application/vnd.oasis.opendocument.text";
                case WFormatType.Markdown:return "text/markdown";
                default:                  return "application/octet-stream";
            }
        }
    }
}
