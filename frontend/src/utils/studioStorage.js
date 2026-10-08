// Server API helpers for the simplified Vue studio. The Python wrapper
// (app.py) hosts both the spreadsheet and the migrated document-editor
// / AI / studio endpoints on a single Flask process. The original
// ASP.NET Core service under Server-side/ is kept as a reference only
// and is no longer required at runtime.

import { DOCUMENT_EDITOR_BASE_URL } from '../data/sampleTemplates.js';

const DOC_EDITOR_IMPORT_FILE_URL = `${DOCUMENT_EDITOR_BASE_URL}/api/DocumentEditor/ImportFileURL`;
const DOC_EDITOR_SAVE_URL = `${DOCUMENT_EDITOR_BASE_URL}/api/DocumentEditor/Save`;
const DOC_EDITOR_MAILMERGE_URL = `${DOCUMENT_EDITOR_BASE_URL}/api/DocumentEditor/MailMerge`;
const DOC_EDITOR_EXPORT_URL = `${DOCUMENT_EDITOR_BASE_URL}/api/DocumentEditor/Export`;
const DOC_EDITOR_SYSTEM_CLIPBOARD_URL = `${DOCUMENT_EDITOR_BASE_URL}/api/DocumentEditor/SystemClipboard`;
const STUDIO_API = `${DOCUMENT_EDITOR_BASE_URL}/api/studio`;

// Build an absolute `${DOCUMENT_EDITOR_BASE_URL}/Templates/<slug>.docx`
// URL from a bare template file name.
export function absoluteDocxUrl(docxUrl) {
  if (!docxUrl) return '';
  if (/^[a-z][a-z0-9+.-]*:\/\//i.test(docxUrl)) return docxUrl;
  if (docxUrl.startsWith('/')) {
    return `${DOCUMENT_EDITOR_BASE_URL}${docxUrl}`;
  }
  return `${DOCUMENT_EDITOR_BASE_URL}/Templates/${docxUrl}`;
}

// Import a server-side .docx into SFDT via ImportFileURL. Returns
// { sfdt, mergeFields } where mergeFields is the live list of MERGEFIELD
// names actually present in the .docx.
export async function fetchSfdtFromDocx({ url, name }) {
  const res = await fetch(DOC_EDITOR_IMPORT_FILE_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json;charset=UTF-8' },
    body: JSON.stringify({ fileUrl: url }),
  });
  if (!res.ok) {
    let detail = '';
    try { detail = await res.text(); } catch { /* ignore */ }
    throw new Error(
      `ImportFileURL failed (${res.status})${detail ? `: ${detail.slice(0, 240)}` : ''}`,
    );
  }
  const raw = await res.text();
  if (!raw) throw new Error('ImportFileURL returned an empty document.');
  try {
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === 'object' && typeof parsed.sfdt === 'string') {
      return {
        sfdt: parsed.sfdt,
        mergeFields: Array.isArray(parsed.mergeFields) ? parsed.mergeFields : [],
      };
    }
  } catch {
    // not JSON — fall through to legacy plain-string handling
  }
  return { sfdt: raw, mergeFields: [] };
}

// Serialize the editor's SFDT and POST it to the backend's
// DocumentEditorController.Save endpoint with a SaveParameter
// { Content, FileName, Format: 'Docx' } body. Saving with the same
// FileName replaces the existing file in wwwroot/Templates/.
export async function saveTemplateToServer({ sfdtContent, documentName, format = 'Docx' }) {
  if (typeof sfdtContent !== 'string' || sfdtContent.length === 0) {
    throw new Error('saveTemplateToServer: sfdtContent is required');
  }
  const fileName = String(documentName || 'Document').replace(/\.docx$/i, '').trim() || 'Document';
  const res = await fetch(DOC_EDITOR_SAVE_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ Content: sfdtContent, FileName: fileName, Format: format }),
  });
  if (!res.ok) {
    let detail = '';
    try { detail = await res.text(); } catch { /* ignore */ }
    throw new Error(
      `Save failed (${res.status})${detail ? `: ${detail.slice(0, 200)}` : ''}`,
    );
  }
  return { ok: true, fileName, format };
}

// Serialize the editor's SFDT and POST it to the backend's
// DocumentEditorController.Export endpoint with a SaveParameter
// { Content, FileName, Format: 'Pdf' } body. The server returns the
// rendered PDF as a binary attachment. The caller can choose to either
// trigger a browser download (default) or read the blob directly
// via { returnBlob: true }.
export async function exportDocumentToPdf({ sfdtContent, documentName, returnBlob = false }) {
  if (typeof sfdtContent !== 'string' || sfdtContent.length === 0) {
    throw new Error('exportDocumentToPdf: sfdtContent is required');
  }
  const baseName = String(documentName || 'Document').replace(/\.docx$/i, '').trim() || 'Document';
  const res = await fetch('https://document.syncfusion.com/web-services/docx-editor/api/documenteditor/Export', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      Content: sfdtContent,
      FileName: `${baseName}`,
      Format: '.Pdf',
    }),
  });
  if (!res.ok) {
    let detail = '';
    try { detail = await res.text(); } catch { /* ignore */ }
    throw new Error(
      `Export PDF failed (${res.status})${detail ? `: ${detail.slice(0, 200)}` : ''}`,
    );
  }
  const blob = await res.blob();
  if (returnBlob) {
    return { ok: true, fileName: `${baseName}.pdf`, blob };
  }
  // Trigger a browser download by creating a temporary <a> element.
  const downloadUrl = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = downloadUrl;
  a.download = `${baseName}.pdf`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  // Free the object URL on the next tick (Safari needs the click to
  // finish first).
  setTimeout(() => URL.revokeObjectURL(downloadUrl), 0);
  return { ok: true, fileName: `${baseName}.pdf` };
}

// POST { fileName, documentData (base64 Data URL), mailMergeData } to the
// backend's MailMerge endpoint and return the merged SFDT. mailMergeData is
// OPTIONAL: when it's omitted/empty the server falls back to converting
// wwwroot/Data/Property Portfolio Data.xlsx (XlsIO SaveAsJson) and merges from it.
export async function mailMergePreview({ fileName, documentData, mailMergeData = '' }) {
  if (typeof documentData !== 'string' || documentData.length === 0) {
    throw new Error('mailMergePreview: documentData (base64) is required');
  }
  const safeFileName = (fileName || 'Document.docx').endsWith('.docx')
    ? (fileName || 'Document.docx')
    : `${(fileName || 'Document').replace(/\.docx$/i, '')}.docx`;
  const res = await fetch(DOC_EDITOR_MAILMERGE_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json;charset=UTF-8' },
    body: JSON.stringify({ fileName: safeFileName, documentData, mailMergeData }),
  });
  if (res.status === 200) {
    const sfdt = await res.text();
    if (!sfdt) throw new Error('Mail merge returned an empty document.');
    return sfdt;
  }
  let detail = '';
  try { detail = await res.text(); } catch { /* ignore */ }
  throw new Error(
    `Mail merge failed (${res.status})${detail ? `: ${detail.slice(0, 240)}` : ''}`,
  );
}

// POST { content, type } to the backend's SystemClipboard endpoint and
// return the resulting SFDT JSON. The server converts HTML / RTF /
// plain text (using Syncfusion.EJ2.WordEditor's LoadString) into the
// SFDT format the client can paste into the document with full
// formatting preserved (bold, italic, lists, headings, links, etc.).
// This is the same endpoint the editor uses internally when
// `enableLocalPaste=false` is set, but we also call it directly from
// the AI rewrite dialog to insert the AI's HTML output without
// losing formatting (editor.editor.insertText() drops formatting).
//
// type defaults to "html"; pass "rtf" or "txt" for other inputs.
// Returns an empty string when the server returns an empty body
// (which signals "no content to paste"); throws on HTTP errors.
export async function systemClipboard({ content, type = 'html' }) {
  if (typeof content !== 'string' || content.length === 0) return '';
  const res = await fetch(DOC_EDITOR_SYSTEM_CLIPBOARD_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json;charset=UTF-8' },
    body: JSON.stringify({ content, type }),
  });
  if (res.status === 200) {
    const sfdt = await res.text();
    return sfdt || '';
  }
  let detail = '';
  try { detail = await res.text(); } catch { /* ignore */ }
  throw new Error(
    `SystemClipboard failed (${res.status})${detail ? `: ${detail.slice(0, 240)}` : ''}`,
  );
}

// Read a Blob (from documentEditor.saveAsBlob('Docx')) as a base64 Data URL.
export function readBlobAsDataUrl(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error || new Error('FileReader failed'));
    reader.readAsDataURL(blob);
  });
}

// POST a custom common-scope merge field to the server's StudioController
// (written to wwwroot/Data/common-merge-fields.json).
export async function addCommonMergeField({ key }) {
  const fd = new FormData();
  fd.append('scope', 'common');
  fd.append('key', key);
  const res = await fetch(`${STUDIO_API}/mergefield`, { method: 'POST', body: fd });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || `Add field failed (${res.status})`);
  }
  const json = await res.json();
  if (!json.ok) throw new Error(json.error || 'Add field failed');
  return json;
}

// GET the common (global) custom merge-field catalog from the server.
export async function fetchCommonMergeFields() {
  try {
    const res = await fetch(`${STUDIO_API}/common-fields`);
    if (!res.ok) return {};
    const json = await res.json();
    return json.fields || {};
  } catch {
    return {};
  }
}