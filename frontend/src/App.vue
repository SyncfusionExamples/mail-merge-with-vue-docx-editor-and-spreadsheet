<script setup>
// Simplified Template Studio — Vue 3 (Composition API).
// No template list UI: the homepage IS the document editor. On mount it
// loads the default .docx from the ASP.NET Core service into a Syncfusion
// DocumentEditor (Ribbon toolbar, always editable) and keeps every other
// function: Save and Publish, Download, Preview with Data (mail merge),
// and the Merge Fields side panel (click/drag insert + Add Field).
import { computed, onMounted, provide, ref } from 'vue';
import {
  DocumentEditorContainerComponent,
  Toolbar,
  Ribbon,
} from '@syncfusion/ej2-vue-documenteditor';
import { DialogComponent } from '@syncfusion/ej2-vue-popups';
import {
  DOCUMENT_EDITOR_SERVICE_URL,
  DEFAULT_TEMPLATE_DOCX,
} from './data/sampleTemplates.js';
import {
  absoluteDocxUrl,
  fetchSfdtFromDocx,
  saveTemplateToServer,
  exportDocumentToPdf,
  mailMergePreview,
  readBlobAsDataUrl,
  fetchCommonMergeFields,
} from './utils/studioStorage.js';
import MergeFieldsPanel from './components/MergeFieldsPanel.vue';
import SmartAIAssistPane from './components/SmartAIAssistPane.vue';
import SpreadsheetComponent from './components/SpreadsheetComponent.vue';
import { MERGE_FIELD_MIME, MERGE_FIELD_PAYLOAD_MIME } from './components/MergeFieldsPanelMime.js';

// Vue 3 module registration for the DocumentEditorContainer (the
// `.Inject()` static from the React package doesn't exist in ej2-vue —
// modules are provided via Vue's provide() instead). The Ribbon module
// is REQUIRED for toolbarMode="Ribbon" — without it the ribbon toolbar
// does not render.
provide('DocumentEditorContainer', [Toolbar, Ribbon]);

const containerRef = ref(null);

// dirty = the document has unsaved edits; the Save button is disabled
// until the user actually changes something (contentChange event).
const dirty = ref(false);
// While the document is being opened programmatically, contentChange must
// not mark it dirty.
const isLoading = ref(true);
const isLoadingDoc = ref(true);
const loadError = ref('');

const isSaving = ref(false);
const isDownloading = ref(false);
const isExportingPdf = ref(false);

// Edit-Excel dialog state: when `isExcelOpen` is true the
// SpreadsheetComponent is mounted inside a modal Syncfusion Dialog and
// the Python service's rentRollDetails.xlsx is loaded into it. The
// dialog's header has a "Back" button that flips this back to false.
const isExcelOpen = ref(false);
function openExcelEditor() {
  isExcelOpen.value = true;
}
function closeExcelEditor() {
  isExcelOpen.value = false;
}

// Called the moment the modal Syncfusion Dialog finishes opening. We
// just log here — the SpreadsheetComponent's own `created` hook handles
// loading rentRollDetails.xlsx from the Python service.
function onExcelDialogOpen() {
  // eslint-disable-next-line no-console
  console.log('[studio] Excel editor dialog opened');
}

// Merge-field state: doc-only MERGEFIELDs returned by ImportFileURL +
// the server-side common (global) custom fields catalog.
const documentMergeFields = ref([]);
const commonFields = ref({});

const docxUrl = absoluteDocxUrl(DEFAULT_TEMPLATE_DOCX);
// Slug used as the Save FileName so a save overwrites the same .docx the
// editor loads on reopen (e.g. "Donation_Thank-You_Letter").
const docxBaseName = DEFAULT_TEMPLATE_DOCX.replace(/\.docx$/i, '').trim();

function getEditor() {
  const inst = containerRef.value;
  if (!inst) return null;
  // ej2-vue container ref: the inner DocumentEditor is at
  // inst.ej2Instances?.documentEditor ?? inst.documentEditor.
  return inst.ej2Instances?.documentEditor ?? inst.documentEditor ?? null;
}

// Called by the DocumentEditorContainer's `created` event — fetches the
// server-side .docx as SFDT and opens it in the editor.
async function handleCreated() {
  const de = getEditor();
  if (!de) return;
  dirty.value = false;
  de.isReadOnly = false;
  de.restrictEditing = false;
  isLoading.value = true;
  try {
    const { sfdt, mergeFields } = await fetchSfdtFromDocx({ url: docxUrl });
    documentMergeFields.value = Array.isArray(mergeFields) ? mergeFields : [];
    de.open(sfdt);
  } catch (err) {
    // eslint-disable-next-line no-console
    console.error('DOCX import failed:', err);
    loadError.value = `Could not load "${DEFAULT_TEMPLATE_DOCX}" from the server. ${err.message || err}`;
    de.openBlank();
  } finally {
    isLoading.value = false;
    isLoadingDoc.value = false;
  }
}

onMounted(async () => {
  commonFields.value = await fetchCommonMergeFields();
});

// contentChange: mark dirty only on real user edits (not programmatic open).
function handleContentChange() {
  if (isLoading.value) return;
  dirty.value = true;
}

// ---- AI pane accessors (exposed to AIPane via props) ----
// Generalized insert (the reference sample's insertContent pattern):
// focus, then insertText with the full plain payload — the editor handles
// newlines inside the text as line breaks.
function insertText(text) {
  const de = getEditor();
  if (!de) return;
  try {
    de.focusIn();
    de.editor.insertText(text);
  } catch (err) {
    // eslint-disable-next-line no-console
    console.warn('insertText failed:', err);
  }
}

function getSelectionText() {
  try {
    return (getEditor()?.selection?.text || '').trim();
  } catch {
    return '';
  }
}

// Insert a merge field at the caret using the editor's API.
function insertField(key) {
  const de = getEditor();
  if (!de) return;
  const fieldName = key.replace(/[\n\r]/g, '');
  const fieldCode = `MERGEFIELD  ${fieldName}  \\* MERGEFORMAT `;
  de.focusIn();
  de.editor.insertField(fieldCode, `«${fieldName}»`);
}

// ----- Custom-field add callback from MergeFieldsPanel -----
function handleCustomFieldAdded(info) {
  commonFields.value = { ...commonFields.value, [info.key]: info.field };
}

// ----- Save flow -----
// Serializes the live document to SFDT and POSTs it to the backend's
// DocumentEditorController.Save endpoint — the same FileName overwrites
// the same .docx the editor loads on startup.
async function handleSave() {
  const de = getEditor();
  if (!de) return;
  isSaving.value = true;
  try {
    let sfdtContent = '';
    try {
      sfdtContent = de.serialize();
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error('serialize SFDT failed:', err);
      throw new Error('Could not serialize the document. Please try again.');
    }
    if (!sfdtContent) throw new Error('Document serialized to an empty payload.');

    const saveResult = await saveTemplateToServer({
      sfdtContent,
      documentName: docxBaseName,
      format: 'Docx',
    });
    // eslint-disable-next-line no-console
    console.log(`[studio] saved via DocumentEditorController.Save -> ${saveResult.fileName}.docx`);
    dirty.value = false;
  } catch (err) {
    // eslint-disable-next-line no-console
    console.error('Save failed:', err);
    alert(`Save failed: ${err.message || err}`);
  } finally {
    isSaving.value = false;
  }
}

// ----- Download flow -----
async function handleDownload() {
  const de = getEditor();
  if (!de) return;
  const baseName = docxBaseName.replace(/[^A-Za-z0-9-_]+/g, '_').replace(/^_+|_+$/g, '') || 'Document';
  isDownloading.value = true;
  try {
    de.save(baseName, 'Docx');
  } catch (err) {
    // eslint-disable-next-line no-console
    console.error('Download failed:', err);
    alert(`Download failed: ${err.message || err}`);
  } finally {
    setTimeout(() => { isDownloading.value = false; }, 800);
  }
}

// ----- Export to PDF flow -----
// Serializes the live document to SFDT, POSTs it to the backend's
// /api/DocumentEditor/Export endpoint with Format='Pdf', and lets the
// browser download the resulting PDF. The export uses the
// DocIORenderer on the server side (no client-side rendering needed).
async function handleExportPdf() {
  const de = getEditor();
  if (!de) return;
  isExportingPdf.value = true;
  try {
    let sfdtContent = '';
    try {
      sfdtContent = de.serialize();
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error('serialize SFDT failed:', err);
      throw new Error('Could not serialize the document. Please try again.');
    }
    if (!sfdtContent) throw new Error('Document serialized to an empty payload.');

    const result = await exportDocumentToPdf({
      sfdtContent,
      documentName: docxBaseName,
    });
    // eslint-disable-next-line no-console
    console.log(`[studio] exported via DocumentEditorController.Export -> ${result.fileName}`);
  } catch (err) {
    // eslint-disable-next-line no-console
    console.error('Export PDF failed:', err);
    alert(`Export PDF failed: ${err.message || err}`);
  } finally {
    isExportingPdf.value = false;
  }
}

// ----- Preview with Excel data (mail merge) -----
// No popup / JSON upload anymore: clicking the button sends the document
// to the backend WITHOUT mailMergeData — the server reads
// wwwroot/Data/CRE_Appraisal_POC.xlsx, converts it via XlsIO's
// SaveAsJson, and merges. The merged result opens straight in the editor.
const isMerging = ref(false);
const mergeError = ref('');

async function handlePreviewWithExcel() {
  const de = getEditor();
  if (!de) return;
  isMerging.value = true;
  mergeError.value = '';
  try {
    const blob = await de.saveAsBlob('Docx');
    const base64DataUrl = await readBlobAsDataUrl(blob);
    const mergedSfdt = await mailMergePreview({
      fileName: `${docxBaseName}.docx`,
      documentData: base64DataUrl,
      // Intentionally omitted: the server falls back to
      // wwwroot/Data/CRE_Appraisal_POC.xlsx when mailMergeData is empty.
      mailMergeData: '',
    });
    de.open(mergedSfdt);
    dirty.value = false;
  } catch (err) {
    // eslint-disable-next-line no-console
    console.error('Mail merge preview failed:', err);
    mergeError.value = err.message || String(err) || 'Mail merge failed.';
  } finally {
    isMerging.value = false;
  }
}

// ----- Drag-and-drop from MergeFieldsPanel into the editor canvas -----
const isDragOver = ref(false);
let dragDepth = 0;

function isMergeFieldDrag(dt) {
  if (!dt || !dt.types) return false;
  const types = Array.from(dt.types);
  return types.includes(MERGE_FIELD_MIME) || types.includes(MERGE_FIELD_PAYLOAD_MIME);
}

function readMergeFieldKey(dt) {
  if (!dt) return null;
  try {
    const envelope = dt.getData(MERGE_FIELD_PAYLOAD_MIME);
    if (envelope) {
      const parsed = JSON.parse(envelope);
      if (parsed && parsed.source === 'merge-fields-panel' && typeof parsed.key === 'string') {
        return parsed.key;
      }
    }
  } catch { /* fall through */ }
  const dedicated = dt.getData(MERGE_FIELD_MIME);
  if (dedicated) return dedicated;
  if (isMergeFieldDrag(dt)) return dt.getData('text/plain');
  return null;
}

function handleCanvasDragEnter(e) {
  if (!isMergeFieldDrag(e.dataTransfer)) return;
  e.preventDefault();
  dragDepth += 1;
  isDragOver.value = true;
}

function handleCanvasDragOver(e) {
  if (!isMergeFieldDrag(e.dataTransfer)) return;
  e.preventDefault();
  if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy';
}

function handleCanvasDragLeave() {
  dragDepth = Math.max(0, dragDepth - 1);
  if (dragDepth === 0) isDragOver.value = false;
}

function handleCanvasDrop(e) {
  if (!isMergeFieldDrag(e.dataTransfer)) return;
  e.preventDefault();
  e.stopPropagation();
  dragDepth = 0;
  isDragOver.value = false;
  const key = readMergeFieldKey(e.dataTransfer);
  if (!key) return;
  const de = getEditor();
  try {
    if (de && typeof de.focusIn === 'function') de.focusIn();
    // Best-effort caret placement at the drop point; if it fails we fall
    // back to the editor's existing caret via insertField below.
    if (de && de.selection && typeof de.selection.select === 'function') {
      const rootEl = containerRef.value?.$el;
      const dropX = e.clientX;
      const dropY = e.clientY;
      let viewer = null;
      if (rootEl) {
        const candidates = [
          '.e-de-viewer', '.e-de-page-content', '.e-de-page-container',
          '.e-de-scroll-container', '.e-documenteditor',
          '.e-documenteditor-content', '.e-documenteditor-container',
        ];
        for (const c of candidates) {
          const el = rootEl.querySelector ? rootEl.querySelector(c) : null;
          if (!el || !el.getBoundingClientRect) continue;
          const r = el.getBoundingClientRect();
          if (r.width > 0 && r.height > 0
            && dropX >= r.left && dropX <= r.right
            && dropY >= r.top && dropY <= r.bottom) {
            viewer = el;
            break;
          }
        }
        if (!viewer) viewer = rootEl;
      }
      if (viewer && viewer.getBoundingClientRect) {
        const rect = viewer.getBoundingClientRect();
        const localX = dropX - rect.left;
        const localY = dropY - rect.top;
        let sLeft = 0;
        let sTop = 0;
        try {
          if (typeof viewer.scrollLeft === 'number' && viewer.scrollLeft !== 0) {
            sLeft = viewer.scrollLeft;
          } else {
            let p = viewer.parentElement;
            while (p && !(p.scrollLeft || p.scrollTop)) p = p.parentElement;
            if (p) { sLeft = p.scrollLeft || 0; sTop = p.scrollTop || 0; }
          }
        } catch { /* ignore */ }
        de.selection.select({
          x: Math.max(0, localX + sLeft),
          y: Math.max(0, localY + sTop),
          extend: false,
        });
      }
    }
  } catch (selErr) {
    // eslint-disable-next-line no-console
    console.warn('Drop caret placement failed; using existing caret:', selErr);
  }
  try {
    insertField(key);
  } catch (err) {
    // eslint-disable-next-line no-console
    console.error('Drop-insert failed:', err);
  }
}
</script>

<template>
  <div class="ts-app">
    <header class="ts-viewer-head">
      <div class="ts-viewer-title">
        <h2>Document Merge Preview</h2>
      </div>
      <div class="ts-viewer-actions">
        <button
          type="button"
          class="ts-head-btn"
          :disabled="isMerging"
          title="Mail-merge the document with the server-side Excel data (CRE_Appraisal_POC.xlsx)."
          @click="handlePreviewWithExcel"
        >{{ isMerging ? 'Merging…' : 'Preview with Data' }}</button>
        <button
          type="button"
          class="ts-head-btn"
          :title="isExcelOpen ? 'Close the Excel editor.' : 'Open the rent-roll Excel workbook in a modal editor.'"
          @click="openExcelEditor"
        >Edit Excel</button>
        <button
          type="button"
          class="ts-head-btn ts-head-btn-primary"
          :disabled="isSaving || !dirty"
          title="Save and publish the document."
          @click="handleSave"
        >{{ isSaving ? 'Saving…' : 'Save and Publish' }}</button>
        <button
          type="button"
          class="ts-head-btn"
          :disabled="isDownloading"
          title="Download the document content."
          @click="handleDownload"
        >{{ isDownloading ? 'Preparing…' : 'Download' }}</button>
        <button
          type="button"
          class="ts-head-btn"
          :disabled="isExportingPdf"
          title="Export the document to PDF (rendered server-side via DocIORenderer)."
          @click="handleExportPdf"
        >{{ isExportingPdf ? 'Exporting…' : 'Export to PDF' }}</button>
      </div>
    </header>

    <div class="ts-viewer-body">
      <!-- Smart AI Assist view (left): chat conversation + suggestions. -->
      <SmartAIAssistPane
        :getEditor="getEditor"
        :getSelectionText="getSelectionText"
        :insertText="insertText"
      />
      <div
        class="ts-viewer-canvas"
        :class="{ 'ts-viewer-canvas--drag-over': isDragOver }"
        @dragenter="handleCanvasDragEnter"
        @dragover="handleCanvasDragOver"
        @dragleave="handleCanvasDragLeave"
        @drop="handleCanvasDrop"
      >
        <p v-if="isLoadingDoc" class="ts-loading">Loading document…</p>
        <p v-if="loadError" class="ts-load-error">{{ loadError }}</p>
        <!-- Syncfusion DocumentEditorContainer — built-in Word-like ribbon,
             always in Edit mode, loads the default .docx on `created`. -->
        <DocumentEditorContainerComponent
          ref="containerRef"
          height="100%"
          width="100%"
          :enableToolbar="true"
          :toolbarMode="'Ribbon'"
          :showPropertiesPane="false"
          :serviceUrl="DOCUMENT_EDITOR_SERVICE_URL"
          @created="handleCreated"
          @contentChange="handleContentChange"
        />
      </div>

      <MergeFieldsPanel
        :commonFieldsProp="commonFields"
        :documentMergeFields="documentMergeFields"
        @insert-field="insertField"
        @custom-field-added="handleCustomFieldAdded"
      />
    </div>

    <!-- Merge error toast (replaces the old JSON-upload modal). -->
    <p v-if="mergeError" class="ts-load-error" role="alert">{{ mergeError }}</p>

    <!-- Edit Excel modal: hosts the SpreadsheetComponent (which loads
         rentRollDetails.xlsx from the Python service on `created`). The
         "Back" button in the dialog header is the only way to close it,
         so the user always returns to the document editor in the same
         state. We use v-if (not v-show) so the spreadsheet is
         freshly created every time the dialog opens. -->
    <DialogComponent
      v-if="isExcelOpen"
      ref="excelDialog"
      :visible="true"
      :isModal="true"
      :showCloseIcon="true"
      :closeOnEscape="true"
      :width="'90%'"
      :height="'90%'"
      :header="'Edit Excel — CRE_Appraisal_POC.xlsx (shared with Mail Merge)'"
      :allowDragging="true"
      :animationSettings="{ effect: 'Fade', duration: 200, delay: 0 }"
      cssClass="ts-excel-dialog"
      :open="onExcelDialogOpen"
      :close="closeExcelEditor"
    >
      <div class="ts-excel-dialog-body">
        <SpreadsheetComponent />
      </div>
      <!-- Footer with a "Back" button — explicit way to return to the
           document editor without using the close icon. -->
      <template #footer>
        <div class="ts-excel-dialog-footer">
          <button
            type="button"
            class="ts-head-btn ts-head-btn-primary"
            @click="closeExcelEditor"
          >Back to Document</button>
        </div>
      </template>
    </DialogComponent>
  </div>
</template>