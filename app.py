from flask import Flask, json, request, Response, send_file, send_from_directory
from flask_cors import CORS #import CORS from flask_cors

import os
import os as _os  # alias used by the settings loader further down
import re
import sys as _sys
import base64
import json as json_lib
import traceback
import uuid
import datetime
from io import BytesIO

# ============================================================================
# Pythonnet / .NET runtime bootstrap (MUST run before `import clr`).
# ----------------------------------------------------------------------------
# pythonnet only honours PYTHONNET_RUNTIME at module-import time, so we
# set it before the first clr import. We also pin DOTNET_ROOT (in case
# the dev box has no `dotnet` on PATH, e.g. a Windows service install)
# and DOTNET_ROLL_FORWARD=LatestMajor so the wrapper (built for net8.0)
# will load even when the highest installed runtime is 9 or 10 (the host
# picks the highest matching version that's >= 8.0).
# ============================================================================
_os.environ.setdefault("PYTHONNET_RUNTIME", "coreclr")
if not _os.environ.get("DOTNET_ROOT"):
    # Best-effort: pick the newest installed Microsoft.NETCore.App.
    _candidate = None
    for _base in (
        r"C:\Program Files\dotnet\shared\Microsoft.NETCore.App",
        "/usr/share/dotnet/shared/Microsoft.NETCore.App",
        "/usr/local/share/dotnet/shared/Microsoft.NETCore.App",
    ):
        if os.path.isdir(_base):
            _candidate = _base
            break
    if _candidate:
        _os.environ["DOTNET_ROOT"] = _candidate
_os.environ.setdefault("DOTNET_ROLL_FORWARD", "LatestMajor")

# Import clr AFTER the env-var setup above.
import clr  # noqa: E402  (must come after PYTHONNET_RUNTIME setup)

app = Flask(
__name__,
static_folder='frontend/dist',
static_url_path=''
)

# ---- Minimal CORS + large-file support ----
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024 # 500 MB
app.config['MAX_FORM_MEMORY_SIZE'] = 500 * 1024 * 1024 # 500 MB


CORS(
    app,
    resources={r"/*": {"origins": "*"}},
    supports_credentials=False,
    expose_headers=["Content-Disposition", "Content-Length", "Content-Type"],
)

# Force CORS headers on EVERY response (including 413/500 errors)
@app.after_request
def add_cors_on_errors(resp):
    resp.headers["Access-Control-Allow-Origin"]  = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, PUT, DELETE"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return resp
# -------------------------------------------

# ============================================================================
# Filesystem layout
# ----------------------------------------------------------------------------
#   <cwd>/.NET Standard Wrapper Library/WebServiceLibrary/bin/Release/net8.0/publish/
#       Compiled .NET wrappers (Spreadsheet + DocumentEditor).
#   <cwd>/Files/Templates/
#       The .docx templates the DocumentEditor opens by default
#       (mirrors the C# project's wwwroot/Templates folder).
#   <cwd>/Files/Data/
#       The catalog + common-merge-fields JSON + the **shared**
#       mail-merge Excel data file. The same file is the data source
#       for the SpreadsheetComponent (`/OpenRentRoll` and
#       `/SaveRentRoll` write to it in place) AND for the DocumentEditor's
#       `/MailMerge` endpoint (which falls back to it when no inline
#       mailMergeData is provided). Single source of truth, in-place
#       edits stay in sync between the two editor surfaces.
# ============================================================================
current_working_directory = os.getcwd()
publish_base = (
    current_working_directory
    + "/.NET Standard Wrapper Library/WebServiceLibrary/bin/Release/net8.0/publish/"
)
files_root     = os.path.join(current_working_directory, "Files")
templates_root = os.path.join(files_root, "Templates")
data_root      = os.path.join(files_root, "Data")

# The single Excel data file shared by the SpreadsheetComponent and the
# DocumentEditor mail-merge. Both editor surfaces edit this file in
# place; the SpreadsheetComponent's "Save" overwrites the same file
# that MailMerge reads on its next call.
SHARED_DATA_FILE  = "CRE_Appraisal_POC.xlsx"
SHARED_DATA_PATH  = os.path.join(data_root, SHARED_DATA_FILE)

# Make sure the runtime folders exist (idempotent).
os.makedirs(templates_root, exist_ok=True)
os.makedirs(data_root, exist_ok=True)

# ============================================================================
# Load the .NET wrapper assemblies via pythonnet.
# ----------------------------------------------------------------------------
# We add the publish folder to sys.path so pythonnet can locate
# every DLL by simple name. The .NET 8 BCL types (System.Buffers,
# System.Memory, Microsoft.Bcl.AsyncInterfaces, System.Text.Json, etc.)
# are resolved automatically by the .NET 8 host — we don't need to
# AddReference them explicitly.
# ============================================================================
# On Windows, pythonnet's bundled .NET 8 runtime sometimes fails to
# auto-resolve runtimes/<rid>/native/libSkiaSharp.dll on its own.
# Adding the native folder to PATH at startup makes SkiaSharp
# (and therefore DocIORenderer + the spreadsheet) load cleanly in
# dev. The Docker image already has the right system libraries.
_native_dir = os.path.join(publish_base, "runtimes", "win-x64", "native")
if os.path.isdir(_native_dir):
    os.environ["PATH"] = _native_dir + os.pathsep + os.environ.get("PATH", "")

_sys.path.insert(0, publish_base)

_ASSEMBLY_NAMES = [
    "Syncfusion.EJ2.Spreadsheet",
    "Syncfusion.EJ2.DocumentEditor",
    "BitMiracle.LibTiff.NET",
    "HarfBuzzSharp",
    "Newtonsoft.Json",
    "SkiaSharp",
    "SkiaSharp.HarfBuzz",
    "Syncfusion.Compression.Portable",
    "Syncfusion.DocIO.Portable",
    "Syncfusion.DocIORenderer.Portable",
    "Syncfusion.Licensing",
    "Syncfusion.MetafileRenderer.Portable",
    "Syncfusion.OfficeChart.Portable",
    "Syncfusion.Pdf.Imaging.Portable",
    "Syncfusion.Pdf.Portable",
    "Syncfusion.SkiaSharpHelper.Portable",
    "Syncfusion.XlsIO.Portable",
    "Syncfusion.XlsIORenderer.Portable",
    # Syncfusion's EJ2 Spreadsheet does a literal Assembly.Load on the
    # ASP.NET Core 2.3 Mvc facade. These come from the .csproj's
    # PackageReference entries and are published into the same folder
    # by `dotnet publish` — load them before WebServiceLibrary so the
    # SpreadsheetEditor's Save() path resolves them.
    "Microsoft.AspNetCore.Mvc.Core",
    "Microsoft.AspNetCore.Mvc.Abstractions",
    "WebServiceLibrary",
]

for _name in _ASSEMBLY_NAMES:
    clr.AddReference(_name)

# ============================================================================
# Python-side imports from the C# wrapper namespace.
# ============================================================================
from WebServiceLibrary import SpreadsheetEditor, DocumentEditor
from Syncfusion.EJ2.Spreadsheet import SaveSettings, SaveType
from Syncfusion.Licensing import SyncfusionLicenseProvider
from System import Enum
from System.IO import SeekOrigin

# ---------------------------------------------------------------------------
# Configuration
# ----------
# All runtime config lives in appsettings.json (with appsettings.Development.json
# overlaid in dev), the same convention the legacy .NET project used.
# Process-level environment variables override file values, so containers
# and CI can still inject keys without touching the JSON.
#
#     appsettings.json              — base settings (committed to git, OK to leave empty)
#     appsettings.Development.json  — dev secrets (recommended: gitignored)
#     SYNCFUSION_LICENSE_KEY        — env-var override
#     AZURE_OPENAI_ENDPOINT         — env-var override
#     AZURE_OPENAI_API_KEY          — env-var override
#     AZURE_OPENAI_DEPLOYMENT       — env-var override
#     AZURE_OPENAI_API_VERSION      — env-var override (defaults to 2024-02-15-preview)
# ---------------------------------------------------------------------------
def _deep_merge(base, overlay):
    """Recursively merge `overlay` into `base`.

    Rules:
      * Nested dicts are merged key-by-key.
      * Empty / None values in the overlay are ignored (they don't
        clobber a real value in the base).
      * Non-empty scalars from the overlay replace the base value.
    """
    if isinstance(base, dict) and isinstance(overlay, dict):
        for k, v in overlay.items():
            if v is None or v == "":
                # Empty overlay value: keep the base.
                continue
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                base[k] = _deep_merge(base[k], v)
            else:
                base[k] = v
    return base

def _load_settings():
    settings = {}
    base = os.path.join(current_working_directory, "appsettings.json")
    dev  = os.path.join(current_working_directory, "appsettings.Development.json")
    for path in (base, dev):
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8-sig") as f:
                    settings = _deep_merge(settings, json_lib.load(f))
            except Exception as e:
                print(f"[app] warning: failed to read {path}: {e}", flush=True)
    # Env-var overlay (only for non-empty values).
    env_overlay = {}
    if _os.environ.get("SYNCFUSION_LICENSE_KEY"):
        env_overlay.setdefault("Syncfusion", {})["LicenseKey"] = _os.environ["SYNCFUSION_LICENSE_KEY"]
    ai_overlay = {}
    for src, dst in (
        ("AZURE_OPENAI_ENDPOINT",   "Endpoint"),
        ("AZURE_OPENAI_API_KEY",    "ApiKey"),
        ("AZURE_OPENAI_DEPLOYMENT", "DeploymentName"),
        ("AZURE_OPENAI_API_VERSION","ApiVersion"),
    ):
        if _os.environ.get(src):
            ai_overlay[dst] = _os.environ[src]
    if ai_overlay:
        env_overlay["AzureOpenAI"] = ai_overlay
    settings = _deep_merge(settings, env_overlay)
    return settings

_settings = _load_settings()

# Convenience accessors (used throughout the rest of this file).
# Each string value is stripped so a stray space in the JSON (e.g.
# `"Endpoint": " https://...`) doesn't break the Azure SDK call.
SYNCFUSION_LICENSE_KEY = (
    (_settings.get("Syncfusion", {}).get("LicenseKey", "") or "").strip()
)
_ai = _settings.get("AzureOpenAI", {})
AI_ENDPOINT    = (_ai.get("Endpoint", "")         or "").strip()
AI_API_KEY     = (_ai.get("ApiKey", "")           or "").strip()
AI_DEPLOYMENT  = (_ai.get("DeploymentName", "")   or "").strip()
AI_API_VERSION = (
    (_ai.get("ApiVersion", "2024-02-15-preview") or "2024-02-15-preview").strip()
)

# Register Syncfusion license. If SYNCFUSION_LICENSE_KEY isn't provided
# the controls render an evaluation watermark — they still work, they
# just look ugly in the browser.
if SYNCFUSION_LICENSE_KEY:
    SyncfusionLicenseProvider.RegisterLicense(SYNCFUSION_LICENSE_KEY)
else:
    print(
        "[app] Syncfusion license key is not set; Syncfusion controls "
        "will show an evaluation watermark. Add it to appsettings.json "
        "under Syncfusion.LicenseKey to remove it.",
        flush=True,
    )

spreadEditor = SpreadsheetEditor()   # Spreadsheet wrapper (existing)
docEditor    = DocumentEditor()      # DocumentEditor wrapper (new)

# ---------------------------------------------------------------------------
# Helpers — JSON I/O for the Studio (catalog + common fields).
# ---------------------------------------------------------------------------
CATALOG_FILE    = os.path.join(data_root, "templates.json")
COMMON_FILE     = os.path.join(data_root, "common-merge-fields.json")
SAFE_ID_RE      = re.compile(r"^[A-Za-z0-9_\-\.]+$")

def _read_json_or(path, default):
    """Read a JSON file or return `default` on any failure.

    Reads as utf-8-sig so a UTF-8 BOM (which PowerShell's
    `Set-Content -Encoding UTF8` writes by default) doesn't trip
    json.loads.
    """
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            text = f.read().strip()
        if not text:
            return default
        return json_lib.loads(text)
    except Exception:
        return default

def _write_json(path, payload):
    """Pretty-print and atomically write JSON to disk."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json_lib.dump(payload, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)

def _coerce_field_keys(value):
    """Coerce a JSON-deserialized value into a List[str] of merge-field keys."""
    if not isinstance(value, list):
        return []
    seen = set()
    out = []
    for v in value:
        if isinstance(v, str) and v and v not in seen:
            seen.add(v)
            out.append(v)
    return out

def _utcnow_iso():
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# ============================================================================
# ---- Spreadsheet endpoints (existing — unchanged) -------------------------
# ============================================================================

@app.route('/Open', methods=['POST'])
def openExcel():
    if 'file' in request.files:
        files = request.files['file']
        # Get the stream data
        print(files)
        stream_data = files.stream.read()
        # Calling our Open method from our SpreadsheetEditor class which will return the Workbook JSON string
        return spreadEditor.Open(stream_data)
    else:
        return ""

@app.route('/Save', methods=['POST'])
def saveExcel():
    try:
        # Extract parameters from form data
        json_data = request.form.get('JSONData', '')
        save_type = request.form.get('saveType', 'Xlsx')  # Default to Xlsx
        file_name = request.form.get('fileName', 'Sample')

        # Extract PDF layout settings if provided
        pdf_layout_settings = request.form.get('pdfLayoutSettings', '{}')

        # Create SaveSettings object
        save_settings = SaveSettings()
        save_settings.JSONData = json_data
        # Convert string to SaveType enum
        save_settings.SaveType = Enum.Parse(SaveType, save_type)
        save_settings.FileName = file_name
        save_settings.PdfLayoutSettings = pdf_layout_settings

        # Call the Save method from SpreadsheetEditor class
        file_stream = spreadEditor.Save(save_settings)

        # Convert .NET MemoryStream to bytes
        file_stream.Seek(0, SeekOrigin.Begin)  # Seek to beginning
        stream_bytes = file_stream.ToArray()  # Convert to byte array
        file_stream.Dispose()  # Clean up the stream

        # Convert bytes to BytesIO for Flask
        output = BytesIO(stream_bytes)
        output.seek(0)

        extension = f".{save_type.lower()}"
        # Get the mime type based on the save type.
        mime_type = {
            "xls":  "application/vnd.ms-excel",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "pdf": "application/pdf",
            "csv": "text/csv"
        }.get(save_type.lower(), "application/octet-stream")

        return send_file(
            output,
            as_attachment=True,
            download_name=f"{file_name}{extension}",
            mimetype=mime_type
        )

    except Exception as e:
        import traceback
        error_msg = f"Error saving file: {str(e)}\n{traceback.format_exc()}"
        print(error_msg)
        return error_msg, 500


@app.route('/OpenRentRoll', methods=['GET'])
def open_rent_roll():
    """
    Server-side file open flow. Reads the SHARED_DATA_FILE that the
    SpreadsheetComponent AND the DocumentEditor mail-merge both use —
    they share a single source of truth.
    """
    try:
        if not os.path.exists(SHARED_DATA_PATH):
            error_payload = json.dumps(
                {"error": f"Shared data file not found: {SHARED_DATA_PATH}"}
            )
            return Response(
                error_payload, status=404, mimetype='application/json'
            )

        with open(SHARED_DATA_PATH, 'rb') as f:
            stream_data = f.read()

        result = spreadEditor.Open(stream_data)
        return Response(result, mimetype='application/json')

    except Exception as e:
        error_msg = (
            f"Error opening shared data file: {str(e)}\n{traceback.format_exc()}"
        )
        print(error_msg)
        error_payload = json.dumps({"error": error_msg})
        return Response(
            error_payload, status=500, mimetype='application/json'
        )


@app.route('/SaveRentRoll', methods=['POST'])
def save_rent_roll():
    """
    Save the shared Excel data file in place. The SpreadsheetComponent
    and the DocumentEditor mail-merge both read this same file, so an
    edit + save in the spreadsheet is immediately visible to the next
    mail-merge call (and vice versa).
    """
    try:
        json_data = request.form.get('JSONData', '')
        save_type = request.form.get('saveType', 'Xlsx')

        # The fileName from the client is purely cosmetic — the save
        # target is always the shared file. We accept it for backward
        # compatibility with the existing frontend but ignore it.
        file_name = SHARED_DATA_FILE.rsplit('.', 1)[0]  # "CRE_Appraisal_POC"

        pdf_layout_settings = request.form.get('pdfLayoutSettings', '{}')

        save_settings = SaveSettings()
        save_settings.JSONData = json_data
        save_settings.SaveType = Enum.Parse(SaveType, save_type)
        save_settings.FileName = file_name
        save_settings.PdfLayoutSettings = pdf_layout_settings

        file_stream = spreadEditor.Save(save_settings)
        file_stream.Seek(0, SeekOrigin.Begin)
        stream_bytes = file_stream.ToArray()
        python_bytes = bytes(bytearray(stream_bytes))
        file_stream.Dispose()

        # Ensure the target directory exists, then overwrite the
        # shared file in place so the next mail-merge picks it up.
        os.makedirs(data_root, exist_ok=True)

        extension = f".{save_type.lower()}"
        # Force the extension to .xlsx regardless of the client-sent
        # fileName — this is the canonical shared data file.
        file_path = os.path.join(data_root, f"{file_name}{extension}")
        # If a non-xlsx save type was requested (csv, xls, pdf), still
        # write the shared data as .xlsx so the mail-merge fallback
        # path (which only knows .xlsx) can find it.
        if save_type.lower() not in ("xlsx", "xls"):
            file_path = SHARED_DATA_PATH

        with open(file_path, 'wb') as f:
            f.write(python_bytes)

        response_payload = json.dumps({
            "success": True,
            "message": f"File saved successfully to {file_path}",
            "filePath": file_path
        })
        return Response(response_payload, status=200, mimetype='application/json')

    except Exception as e:
        error_msg = f"Error saving shared data file: {str(e)}\n{traceback.format_exc()}"
        print(error_msg)
        error_payload = json.dumps({"error": error_msg})
        return Response(
            error_payload, status=500, mimetype='application/json'
        )


# ============================================================================
# ---- DocumentEditor endpoints (NEW — mirror the C# controller) ------------
# ============================================================================
# The Syncfusion EJ2 DocumentEditor container talks to a service URL it
# expects to find these endpoints under. We register them as POST routes
# (the same contract the original DocumentEditorController used).
# ============================================================================

@app.route("/api/DocumentEditor/Import", methods=["POST"])
def de_import():
    """
    Mirror of DocumentEditorController.Import — accept a multipart
    "file" upload, return the SFDT JSON string.
    """
    try:
        if "file" not in request.files:
            return Response("", status=400, mimetype="text/plain")
        f = request.files["file"]
        file_bytes = f.read()
        if not file_bytes:
            return Response("", status=400, mimetype="text/plain")
        result = docEditor.ImportFromBytes(file_bytes, f.filename or "Document.docx")
        return Response(result, status=200, mimetype="application/json")
    except Exception as e:
        return Response(
            json.dumps({"error": str(e), "trace": traceback.format_exc()}),
            status=500, mimetype="application/json",
        )


@app.route("/api/DocumentEditor/ImportFileURL", methods=["POST"])
def de_import_file_url():
    """
    Mirror of DocumentEditorController.ImportFileURL. The Syncfusion
    React/Vue client calls this with a JSON body of
    { fileUrl: "..." } and we return a JSON envelope of
    { sfdt: "<SFDT JSON>", mergeFields: ["Name1", ...] }.
    """
    try:
        body = request.get_json(force=True, silent=False) or {}
        file_url = body.get("fileUrl", "")
        if not file_url:
            return Response(
                json.dumps({"error": "fileUrl is required"}),
                status=400, mimetype="application/json",
            )
        # The C# wrapper returns a 2-element object[]: [sfdt, string[]].
        result = docEditor.ImportFromFileUrl(file_url)
        sfdt = result[0]
        merge_fields = result[1] if len(result) > 1 else []
        return Response(
            json.dumps({"sfdt": sfdt, "mergeFields": list(merge_fields or [])}),
            status=200, mimetype="application/json",
        )
    except Exception as e:
        return Response(
            json.dumps({"error": str(e), "trace": traceback.format_exc()}),
            status=500, mimetype="application/json",
        )


@app.route("/api/DocumentEditor/RestrictEditing", methods=["POST"])
def de_restrict_editing():
    """
    Mirror of DocumentEditorController.RestrictEditing — body
    { passwordBase64, saltBase64, spinCount }, returns the
    WordDocument.ComputeHash string[] as JSON.
    """
    try:
        body = request.get_json(force=True, silent=False) or {}
        pw   = body.get("passwordBase64") or ""
        salt = body.get("saltBase64") or ""
        spin = int(body.get("spinCount") or 0)
        result = docEditor.RestrictEditing(pw, salt, spin)
        return Response(json.dumps(result or []), status=200, mimetype="application/json")
    except Exception as e:
        return Response(
            json.dumps({"error": str(e), "trace": traceback.format_exc()}),
            status=500, mimetype="application/json",
        )


@app.route("/api/DocumentEditor/Save", methods=["POST"])
def de_save():
    """
    Mirror of DocumentEditorController.Save — accept a JSON body
    { Content: "<SFDT>", FileName: "...", Format: "Docx" }, write
    the resulting .docx to <Files>/Templates/<FileName>.docx
    (FileMode.Create — replaces any existing file).
    """
    try:
        body = request.get_json(force=True, silent=False) or {}
        content  = body.get("Content", "") or ""
        file_name = body.get("FileName", "") or ""
        fmt       = body.get("Format", "") or "Docx"
        if not content:
            return Response(
                json.dumps({"error": "Content is required"}),
                status=400, mimetype="application/json",
            )
        docEditor.SaveToFile(content, file_name, fmt, templates_root)
        # Mirror the C# controller's response: it returns void, the
        # React/Vue client treats a 2xx as success.
        return Response("", status=200, mimetype="application/json")
    except Exception as e:
        return Response(
            json.dumps({"error": str(e), "trace": traceback.format_exc()}),
            status=500, mimetype="application/json",
        )


@app.route("/api/DocumentEditor/Export", methods=["POST"])
def de_export():
    """
    Mirror of DocumentEditorController.Export — accept a JSON body
    { Content, FileName, Format }, stream the resulting file as
    an attachment.
    """
    try:
        body = request.get_json(force=True, silent=False) or {}
        content  = body.get("Content", "") or ""
        file_name = body.get("FileName", "") or "Document1.docx"
        fmt       = body.get("Format", "") or ""
        if not content:
            return Response(
                json.dumps({"error": "Content is required"}),
                status=400, mimetype="application/json",
            )
        # The C# wrapper returns a 3-element object[]: [byte[], contentType, fileName].
        result = docEditor.Export(content, file_name, fmt)
        out_bytes = bytes(bytearray(result[0])) if result[0] is not None else b""
        content_type = result[1] or "application/octet-stream"
        suggested_name = result[2] or "Document.docx"
        return send_file(
            BytesIO(out_bytes),
            as_attachment=True,
            download_name=suggested_name,
            mimetype=content_type,
        )
    except Exception as e:
        return Response(
            json.dumps({"error": str(e), "trace": traceback.format_exc()}),
            status=500, mimetype="application/json",
        )


@app.route("/api/DocumentEditor/MailMerge", methods=["POST"])
def de_mail_merge():
    """
    Mirror of DocumentEditorController.MailMerge — body
    { fileName, documentData (base64 Data URL), mailMergeData }.
    Returns the merged SFDT JSON string.
    """
    try:
        body = request.get_json(force=True, silent=False) or {}
        doc_b64  = body.get("documentData", "") or ""
        mm_data  = body.get("mailMergeData", "") or ""
        if not doc_b64:
            return Response(
                json.dumps({"error": "documentData is required"}),
                status=400, mimetype="application/json",
            )
        sfdt = docEditor.MailMerge(doc_b64, mm_data, files_root)
        return Response(sfdt, status=200, mimetype="application/json")
    except Exception as e:
        return Response(
            json.dumps({"error": str(e), "trace": traceback.format_exc()}),
            status=500, mimetype="application/json",
        )


# ---- Static .docx serving for the editor's `serviceUrl`-driven loads ----
# The Syncfusion DocumentEditor container's "ImportFileURL" gets handed
# a relative URL like "/Templates/Donation_Thank-You_Letter.docx"; we
# serve that from <Files>/Templates/ so the catalog's docxUrl field can
# be a simple relative path. The catalog also has absolute URLs we
# generate on download, but absoluteDocxUrl() in studioStorage.js handles
# both.
@app.route("/Templates/<path:filename>", methods=["GET"])
def serve_template(filename):
    """Serve a .docx template from <Files>/Templates/."""
    # Path-traversal guard.
    if ".." in filename or filename.startswith("/") or filename.startswith("\\"):
        return Response("Forbidden", status=403)
    target = os.path.join(templates_root, filename)
    if not os.path.isfile(target):
        return Response("Not found", status=404)
    return send_from_directory(templates_root, filename, as_attachment=False)


# ============================================================================
# ---- AI endpoint (mirror of AIController.Process) -------------------------
# ============================================================================
# Uses the OpenAI Python SDK (or any OpenAI-compatible client) to call
# Azure OpenAI. Credentials are read from env vars so the same image
# works in dev + production. We avoid pulling a hard dependency on the
# `openai` package to keep the runtime small; we hit the REST endpoint
# directly with the standard library.
# ============================================================================
import urllib.request
import urllib.error
import ssl

def _call_azure_openai(messages, model=None):
    """
    POST to Azure OpenAI Chat Completions using urllib (no extra deps).
    Returns the assistant text on success, raises on failure.
    """
    if not (AI_ENDPOINT and AI_API_KEY and AI_DEPLOYMENT):
        raise RuntimeError(
            "Azure OpenAI is not configured. Set AzureOpenAI.Endpoint, "
            "AzureOpenAI.ApiKey, AzureOpenAI.DeploymentName in "
            "appsettings.json (or the matching env vars)."
        )
    # Allow either full URL or base host.
    base = AI_ENDPOINT.rstrip("/")
    url = f"{base}/openai/deployments/{AI_DEPLOYMENT}/chat/completions?api-version={AI_API_VERSION}"
    payload = {
        "messages": messages,
    }
    if model:
        payload["model"] = model
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={
            "Content-Type": "application/json",
            "api-key": AI_API_KEY,
        },
    )
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=120) as resp:
            body = resp.read().decode("utf-8")
            parsed = json.loads(body)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Azure OpenAI HTTP {e.code}: {detail[:500]}"
        ) from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Azure OpenAI network error: {e}") from e

    choices = parsed.get("choices") or []
    if not choices:
        raise RuntimeError("Azure OpenAI returned no choices.")
    msg = choices[0].get("message") or {}
    return msg.get("content", "") or ""


@app.route("/api/DocumentEditor/Process", methods=["POST"])
def ai_process():
    """
    Mirror of AIController.Process — body
    { messages: [{ role, content }, ...], model } and returns
    { Text: "<generated content>" }.
    """
    try:
        if not (AI_ENDPOINT and AI_API_KEY and AI_DEPLOYMENT):
            return Response(
                json.dumps({
                    "error": (
                        "Azure OpenAI is not configured. Set "
                        "AzureOpenAI.Endpoint / AzureOpenAI.ApiKey / "
                        "AzureOpenAI.DeploymentName in appsettings.json "
                        "(or matching env vars)."
                    )
                }),
                status=500, mimetype="application/json",
            )
        body = request.get_json(force=True, silent=False) or {}
        messages = body.get("messages") or []
        model    = body.get("model")
        if not messages:
            return Response(
                json.dumps({"error": "messages are required."}),
                status=400, mimetype="application/json",
            )
        text = _call_azure_openai(messages, model=model)
        return Response(
            json.dumps({"Text": text}),
            status=200, mimetype="application/json",
        )
    except Exception as e:
        return Response(
            json.dumps({"error": "AI request failed: " + str(e)}),
            status=500, mimetype="application/json",
        )


# ============================================================================
# ---- Studio endpoints (mirror of StudioController) ------------------------
# ============================================================================
# Catalog + common merge fields. The .docx files live in
# <Files>/Templates/; their catalog entry's `docxUrl` is a relative
# "/Templates/<file>.docx" so it can be served by the /Templates/
# route above.
# ============================================================================

@app.route("/api/studio/catalog", methods=["GET"])
def studio_catalog_get():
    catalog = _read_json_or(CATALOG_FILE, [])
    if not isinstance(catalog, list):
        catalog = []
    return Response(
        json.dumps(catalog),
        status=200, mimetype="application/json",
    )


@app.route("/api/studio/catalog", methods=["PUT"])
def studio_catalog_put():
    try:
        body = request.get_json(force=True, silent=False)
        if not isinstance(body, list):
            return Response(
                json.dumps({"error": "Catalog body must be a JSON array."}),
                status=400, mimetype="application/json",
            )
        _write_json(CATALOG_FILE, body)
        return Response(
            json.dumps({"ok": True, "count": len(body)}),
            status=200, mimetype="application/json",
        )
    except Exception as e:
        return Response(
            json.dumps({"error": str(e)}),
            status=500, mimetype="application/json",
        )


@app.route("/api/studio/common-fields", methods=["GET"])
def studio_common_fields_get():
    obj = _read_json_or(COMMON_FILE, {"fields": {}})
    if not isinstance(obj, dict) or "fields" not in obj:
        obj = {"fields": {}}
    return Response(
        json.dumps(obj),
        status=200, mimetype="application/json",
    )


@app.route("/api/studio/mergefield", methods=["POST"])
def studio_mergefield_post():
    """
    Add a custom merge field. Mirrors the C# controller's behavior:
      - scope = "common"  -> persist into common-merge-fields.json
      - scope = "template"-> append into the matching entry's fieldKeys
    """
    try:
        form = request.form
        scope      = (form.get("scope") or "").strip()
        key        = (form.get("key") or "").strip()
        templateId = (form.get("templateId") or "").strip()
        if not key:
            return Response(
                json.dumps({"error": "key is required"}),
                status=400, mimetype="application/json",
            )
        if scope not in ("common", "template"):
            return Response(
                json.dumps({"error": 'scope must be "template" or "common"'}),
                status=400, mimetype="application/json",
            )
        if scope == "template" and not templateId:
            return Response(
                json.dumps({"error": "templateId required for template scope"}),
                status=400, mimetype="application/json",
            )
        field = True
        if scope == "common":
            obj = _read_json_or(COMMON_FILE, {"fields": {}})
            fields = obj.get("fields") if isinstance(obj, dict) else {}
            if not isinstance(fields, dict):
                fields = {}
            fields[key] = field
            payload = {"fields": fields, "updatedAt": _utcnow_iso()}
            _write_json(COMMON_FILE, payload)
            return Response(
                json.dumps({"ok": True, "scope": scope, "key": key, "field": field}),
                status=200, mimetype="application/json",
            )

        # scope == "template"
        if not SAFE_ID_RE.match(templateId):
            return Response(
                json.dumps({"error": "Invalid templateId format."}),
                status=400, mimetype="application/json",
            )
        catalog = _read_json_or(CATALOG_FILE, [])
        if not isinstance(catalog, list):
            catalog = []
        created = False
        index_to_replace = -1
        for i, entry in enumerate(catalog):
            if isinstance(entry, dict) and entry.get("id") == templateId:
                index_to_replace = i
                break
        if index_to_replace < 0:
            # Bootstrap a new entry.
            entry = {
                "id": templateId,
                "name": (form.get("templateName") or templateId).strip() or templateId,
                "type": (form.get("templateType") or "General").strip() or "General",
                "description": (form.get("templateDescription") or "Blank letter template.").strip(),
                "fieldKeys": [],
                "createdAt": _utcnow_iso(),
            }
            created = True
        else:
            entry = dict(catalog[index_to_replace])
        # Ensure fieldKeys is a list of strings.
        field_keys = _coerce_field_keys(entry.get("fieldKeys"))
        if key not in field_keys:
            field_keys.append(key)
        entry["fieldKeys"] = field_keys
        entry["updatedAt"] = _utcnow_iso()
        if index_to_replace >= 0:
            catalog[index_to_replace] = entry
        else:
            catalog.append(entry)
        _write_json(CATALOG_FILE, catalog)
        return Response(
            json.dumps({
                "ok": True,
                "scope": scope,
                "key": key,
                "field": field,
                "fieldKeys": field_keys,
                "entry": entry,
                "catalog": catalog,
                "created": created,
            }),
            status=200, mimetype="application/json",
        )
    except Exception as e:
        return Response(
            json.dumps({"error": str(e), "trace": traceback.format_exc()}),
            status=500, mimetype="application/json",
        )


@app.route("/api/studio/upload", methods=["POST"])
def studio_upload():
    """
    Upload a new .docx template. Mirrors the C# controller:
      - form fields: name, type, description, file (.docx)
      - writes the .docx to <Files>/Templates/<slug>.docx
      - appends a new entry to templates.json
    """
    try:
        f = request.files.get("file")
        if not f or not f.filename:
            return Response(
                json.dumps({"error": "file is required"}),
                status=400, mimetype="application/json",
            )
        name = (request.form.get("name") or "").strip()
        if not name:
            name = os.path.splitext(f.filename)[0]
        if not name:
            name = "template"
        ttype = (request.form.get("type") or "General").strip() or "General"
        desc  = (request.form.get("description") or "Uploaded .docx template").strip()
        # Build a safe slug.
        safe = re.sub(r"[^A-Za-z0-9_\-]+", "_", name).strip("_") or "template"
        timestamp = uuid.uuid4().hex[:12]
        slug = f"{safe}-{timestamp}"
        docx_name = f"{slug}.docx"
        docx_path = os.path.join(templates_root, docx_name)
        f.save(docx_path)
        entry = {
            "id": f"tpl-{slug}",
            "name": name,
            "type": ttype,
            "description": desc,
            "fieldKeys": [
                "OrgName", "OrgAddress", "DonorName", "DonorAddress",
                "DonationAmount", "DonationDate",
            ],
            "docxUrl": f"/Templates/{docx_name}",
            "uploadedAt": _utcnow_iso(),
            "updatedAt": _utcnow_iso(),
        }
        catalog = _read_json_or(CATALOG_FILE, [])
        if not isinstance(catalog, list):
            catalog = []
        catalog.append(entry)
        _write_json(CATALOG_FILE, catalog)
        return Response(
            json.dumps({"ok": True, "entry": entry, "docxFileName": docx_name}),
            status=200, mimetype="application/json",
        )
    except Exception as e:
        return Response(
            json.dumps({"error": str(e), "trace": traceback.format_exc()}),
            status=500, mimetype="application/json",
        )


@app.route("/api/studio/template/<template_id>", methods=["DELETE"])
def studio_template_delete(template_id):
    if not SAFE_ID_RE.match(template_id):
        return Response(
            json.dumps({"error": "Invalid id format."}),
            status=400, mimetype="application/json",
        )
    try:
        catalog = _read_json_or(CATALOG_FILE, [])
        if not isinstance(catalog, list):
            return Response(
                json.dumps({"error": "Catalog is not an array."}),
                status=400, mimetype="application/json",
            )
        remaining = []
        found = False
        for entry in catalog:
            if isinstance(entry, dict) and entry.get("id") == template_id:
                found = True
                continue
            remaining.append(entry)
        if not found:
            return Response(
                json.dumps({"error": f"Template '{template_id}' not found in catalog."}),
                status=404, mimetype="application/json",
            )
        _write_json(CATALOG_FILE, remaining)
        return Response(
            json.dumps({"ok": True, "removed": template_id}),
            status=200, mimetype="application/json",
        )
    except Exception as e:
        return Response(
            json.dumps({"error": str(e), "trace": traceback.format_exc()}),
            status=500, mimetype="application/json",
        )


# ---- Static Data (catalog + common-fields) --------------------------------
# Mirrors wwwroot/Data in the C# project so the client can fetch them
# directly as plain JSON. Useful as a debugging escape hatch.
@app.route("/Data/<path:filename>", methods=["GET"])
def serve_data(filename):
    """Serve catalog / common-fields JSON for debugging."""
    if ".." in filename or filename.startswith("/"):
        return Response("Forbidden", status=403)
    target = os.path.join(data_root, filename)
    if not os.path.isfile(target):
        return Response("Not found", status=404)
    return send_from_directory(data_root, filename, as_attachment=False)


# ---------------------------------------------------------------------------
@app.route("/")
def home():
    return "Flask Web API for SpreadsheetEditor + DocumentEditor!"

if __name__ == "__main__":
    # threaded=True so large uploads don't block the dev server
    app.run(host="0.0.0.0", port=5000, threaded=True, debug=True) # http://localhost:5000/
    # app.run(host='', port=5001, debug=True) # http://localhost:5001/
