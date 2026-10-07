<script setup>
// Simplified Template Studio — Vue 3 (Composition API).
// No template list UI: the homepage IS the document editor. On mount it
// loads the default .docx from the Python wrapper service into a
// Syncfusion DocumentEditor (Ribbon toolbar, always editable) and keeps
// every other function: Save and Publish, Download, Export to PDF,
// Preview with Data (mail merge), and the Smart AI Assist pane.
//
// Merge-field handling is now done via a custom "Mail Merge" ribbon
// tab (see addMailMergeRibbon() below) instead of a right-rail panel.
import { nextTick, onMounted, provide, ref } from 'vue';
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
  addCommonMergeField,
} from './utils/studioStorage.js';
import SmartAIAssistPane from './components/SmartAIAssistPane.vue';
import SpreadsheetComponent from './components/SpreadsheetComponent.vue';

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

// ---------------------------------------------------------------------------
// Insert Merge Field dialog (custom Syncfusion DialogComponent).
// Mirrors the ES5 sample: a modal dialog with a TextBox for the field
// name and Insert / Cancel buttons in the footer. `pendingSave` controls
// whether confirming the dialog also POSTs the new key to the common
// catalog (Insert & Save) or only inserts the field (Insert).
// ---------------------------------------------------------------------------
const isInsertFieldOpen = ref(false);
const insertFieldName = ref('');
const insertFieldError = ref('');
let pendingSave = false;     // not a ref — only the open()/confirm() path reads/writes it
let pendingInputEl = null;   // the underlying <input id="field_text"> node, focused on open

function openInsertFieldDialog({ save }) {
  pendingSave = !!save;
  insertFieldName.value = '';
  insertFieldError.value = '';
  isInsertFieldOpen.value = true;
  // Focus the TextBox once the dialog has finished its open animation
  // and the input is in the DOM. Mirrors the ES5 reference that clears
  // and focuses `field_text` right after `insertFieldDialogObj.show()`.
  nextTick(() => {
    const el = document.getElementById('field_text');
    if (el) {
      pendingInputEl = el;
      el.value = '';
      el.focus();
      el.select?.();
    }
  });
}

function closeInsertFieldDialog() {
  isInsertFieldOpen.value = false;
  pendingInputEl = null;
}

function onInsertFieldInput(ev) {
  // Sync the v-model from the underlying <input> on each keystroke
  // (we listen for the native 'input' event because the TextBox is
  // styled as a plain input and we want the simplest data flow).
  insertFieldName.value = ev?.target?.value ?? '';
  if (insertFieldError.value) insertFieldError.value = '';
}

function confirmInsertField() {
  const key = String(insertFieldName.value || '').trim();
  const isValid = /^[A-Za-z][A-Za-z0-9]*$/.test(key);
  if (!isValid) {
    insertFieldError.value =
      'Invalid field name. Use letters and digits only, starting with a letter.';
    return;
  }
  const save = pendingSave;
  closeInsertFieldDialog();
  const de = getEditor();
  if (!de) return;
  // Put the field at the caret BEFORE the dialog is fully torn down so
  // the editor still owns the focus (the ES5 sample calls
  // `container.documentEditor.focusIn()` in `beforeOpen` for the same
  // reason — but in the Vue version focusIn happens as part of
  // insertField()).
  insertField(key);
  if (save) {
    addCommonMergeField({ key }).catch((err) => {
      // eslint-disable-next-line no-console
      console.warn('[studio] could not persist merge field:', err);
    });
  }
}

// EJ2 Dialog `buttons` configuration — mirrors the ES5 reference's
// `buttons: [{ click, buttonModel: { content, cssClass, isPrimary } }]`
// array. The Dialog wrapper exposes `buttons` as a prop, which gets
// passed straight through to the underlying `Dialog.buttons` API and
// rendered in the dialog's footer. Note: using the EJ2 `buttons` API
// (rather than a Vue `#footer` slot — which the DialogComponent does
// not natively support) guarantees the footer actually renders.
const insertFieldDialogButtons = [
  {
    click: () => confirmInsertField(),
    buttonModel: {
      content: 'Ok',
      cssClass: 'e-flat e-primary',
      isPrimary: true,
    },
  },
  {
    click: () => closeInsertFieldDialog(),
    buttonModel: {
      content: 'Cancel',
      cssClass: 'e-flat',
    },
  },
];

// Called the moment the modal Syncfusion Dialog finishes opening. We
// just log here — the SpreadsheetComponent's own `created` hook handles
// loading rentRollDetails.xlsx from the Python service.
function onExcelDialogOpen() {
  // eslint-disable-next-line no-console
  console.log('[studio] Excel editor dialog opened');
}

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
    const { sfdt } = await fetchSfdtFromDocx({ url: docxUrl });
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
  // Mount the custom "Mail Merge" ribbon tab once the container (and
  // its ribbon) is fully ready. The ribbon instance lives on the
  // container's ej2Instances, not on the inner documentEditor.
  await nextTick();
  addMailMergeRibbon();
}

// ---------------------------------------------------------------------------
// Custom ribbon tab — "Mail Merge"
// ---------------------------------------------------------------------------
// Per the Syncfusion "Customize Ribbon" docs, programmatic tabs/buttons
// are added via `container.ribbon.addTab(...)` and
// `container.ribbon.addItem(...)`. We use a Button with a `clicked`
// handler that prompts the user for a merge field name and inserts it
// at the caret via the editor's `insertField` API.
function addMailMergeRibbon() {
  const inst = containerRef.value;
  const ribbon = inst?.ej2Instances?.ribbon ?? inst?.ribbon;
  if (!ribbon || typeof ribbon.addTab !== 'function') {
    console.warn('[studio] ribbon.addTab not available; Mail Merge tab not added');
    return;
  }
  if (ribbon.__tsMailMergeTabAdded) return;  // idempotent
  ribbon.__tsMailMergeTabAdded = true;

  // Open the custom "Insert Merge Field" dialog and (optionally) persist
  // the new key to the server's common catalog on confirm. We don't
  // call insertField() from the ribbon directly — the dialog's Insert
  // button does that, after validating the entered name.
  const openInsertField = () => {
    if (!getEditor()) return;
    openInsertFieldDialog({ save: false });
  };
  const openInsertFieldAndSave = () => {
    if (!getEditor()) return;
    openInsertFieldDialog({ save: true });
  };

  const tab = {
    header: 'Mail Merge',
    id: 'mail_merge_tab',
    groups: [
      {
        header: 'Insert',
        id: 'mail_merge_insert_group',
        collections: [
          {
            items: [
              {
                type: 'Button',
                buttonSettings: {
                  content: 'Insert Merge Field',
                  iconCss: 'sf-icon-InsertMergeField',
                  clicked: openInsertField,
                },
              },
              {
                type: 'Button',
                buttonSettings: {
                  content: 'Insert & Save to Library',
                  iconCss: 'e-icons e-save',
                  clicked: openInsertFieldAndSave,
                },
              },
            ],
          },
        ],
      },
    ],
  };

  // Add the new tab at the end of the ribbon (after Insert, Review,
  // View, etc.) so it doesn't disturb the built-in ordering.
  ribbon.addTab(tab);
}

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
      <div class="ts-viewer-canvas">
        <p v-if="isLoadingDoc" class="ts-loading">Loading document…</p>
        <p v-if="loadError" class="ts-load-error">{{ loadError }}</p>
        <!-- Syncfusion DocumentEditorContainer — built-in Word-like ribbon,
             always in Edit mode, loads the default .docx on `created`.
             The custom "Mail Merge" ribbon tab is added by
             addMailMergeRibbon() in the @created handler. -->
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
    </div>

    <!-- Merge error toast (replaces the old JSON-upload modal). -->
    <p v-if="mergeError" class="ts-load-error" role="alert">{{ mergeError }}</p>

    <!-- Edit Excel modal: hosts the SpreadsheetComponent (which loads
         the shared CRE_Appraisal_POC.xlsx from the Python service on
         `created`). The Syncfusion Dialog controls open/close via the
         `:visible` prop; we drive it from a ref so we can use v-show
         (instead of v-if) to keep the Dialog + Spreadsheet mounted
         across open/close cycles. Using v-if on a Syncfusion dialog
         that owns a Syncfusion component inside it causes a double-
         destroy race during teardown (the child gets unmounted by
         Vue before the parent dialog has finished its own destroy). -->
    <DialogComponent
      v-show="isExcelOpen"
      ref="excelDialog"
      :visible="isExcelOpen"
      :isModal="true"
      :showCloseIcon="true"
      :closeOnEscape="true"
      :width="'90%'"
      :height="'90%'"
      :target="'.ts-app'"
      :header="'Edit Excel'"
      :allowDragging="true"
      :animationSettings="{ effect: 'Fade', duration: 200, delay: 0 }"
      cssClass="ts-excel-dialog"
      :open="onExcelDialogOpen"
      :close="closeExcelEditor"
    >
      <div class="ts-excel-dialog-body">
        <SpreadsheetComponent v-if="isExcelOpen" />
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

    <!-- Insert Merge Field dialog — opens from the "Mail Merge" ribbon
         tab. Modeled on the ES5 reference: a focused TextBox for the
         field name plus Insert / Cancel footer buttons. v-show keeps
         the dialog mounted between opens so we avoid the Syncfusion
         double-destroy race (same reason the Excel dialog above uses
         v-show). -->
    <DialogComponent
      v-show="isInsertFieldOpen"
      ref="insertFieldDialog"
      :visible="isInsertFieldOpen"
      :isModal="true"
      :showCloseIcon="true"
      :closeOnEscape="true"
      :width="'380px'"
      cssClass="ts-insert-field-dialog"
      :target="'.ts-app'"
      :header="'Insert Merge Field'"
      :allowDragging="true"
      :animationSettings="{ effect: 'Fade', duration: 150, delay: 0 }"
      :close="closeInsertFieldDialog"
      :buttons="insertFieldDialogButtons"
    >
      <div class="ts-insert-field-body">
        <label for="field_text" class="ts-insert-field-label">
          Field name
        </label>
        <input
          id="field_text"
          type="text"
          class="e-input ts-insert-field-input"
          placeholder="e.g. Property Name"
          :value="insertFieldName"
          autocomplete="off"
          spellcheck="false"
          @input="onInsertFieldInput"
          @keydown.enter.prevent="confirmInsertField"
          @keydown.esc.prevent="closeInsertFieldDialog"
        />
        <p v-if="insertFieldError" class="ts-insert-field-error">
          {{ insertFieldError }}
        </p>
        <p class="ts-insert-field-hint">
          Letters and digits only, must start with a letter.
        </p>
      </div>
    </DialogComponent>
  </div>
</template>