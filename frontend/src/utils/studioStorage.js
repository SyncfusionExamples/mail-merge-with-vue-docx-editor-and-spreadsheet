// Server API helpers for the simplified Vue studio. The Python wrapper
// (app.py) hosts both the spreadsheet and the migrated document-editor
// / AI / studio endpoints on a single Flask process. The original
// ASP.NET Core service under Server-side/ is kept as a reference only
// and is no longer required at runtime.

import { DOCUMENT_EDITOR_BASE_URL } from '../data/sampleTemplates.js';

const DOC_EDITOR_IMPORT_FILE_URL = `${DOCUMENT_EDITOR_BASE_URL}/api/DocumentEditor/ImportFileURL`;
const DOC_EDITOR_SAVE_URL = `${DOCUMENT_EDITOR_BASE_URL}/api/DocumentEditor/Save`;
const DOC_EDITOR_MAILMERGE_URL = `${DOCUMENT_EDITOR_BASE_URL}/api/DocumentEditor/MailMerge`;
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

// POST { fileName, documentData (base64 Data URL), mailMergeData } to the
// backend's MailMerge endpoint and return the merged SFDT. mailMergeData is
// OPTIONAL: when it's omitted/empty the server falls back to converting
// wwwroot/Data/CRE_Appraisal_POC.xlsx (XlsIO SaveAsJson) and merges from it.
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