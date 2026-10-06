<script setup>
// MergeFieldsPanel: right-rail chip list of merge fields. Click a field to
// insert it at the caret, or drag a chip into the editor canvas. The
// "Add Field" dialog saves a custom common (global) field via the
// server's StudioController.
import { computed, ref, watch, nextTick } from 'vue';
import { addCommonMergeField } from '../utils/studioStorage.js';
import { MERGE_FIELDS } from '../data/sampleTemplates.js';
import { MERGE_FIELD_MIME, MERGE_FIELD_PAYLOAD_MIME } from './MergeFieldsPanelMime.js';

const props = defineProps({
  commonFieldsProp: { type: Object, default: () => ({}) },
  documentMergeFields: { type: Array, default: () => [] },
});
const emit = defineEmits(['insert-field', 'custom-field-added']);

// Built-in catalog + server common fields + doc-only MERGEFIELDs.
const fields = computed(() => {
  const seen = new Set();
  const list = [];
  const sources = [
    ...Object.keys(MERGE_FIELDS),
    ...Object.keys(props.commonFieldsProp || {}),
    ...(Array.isArray(props.documentMergeFields) ? props.documentMergeFields : []),
  ];
  for (const k of sources) {
    const key = String(k);
    if (!key || seen.has(key)) continue;
    seen.add(key);
    list.push({ key });
  }
  return list;
});

// ----- Add-Field dialog state -----
const showAdd = ref(false);
const key = ref('');
const saving = ref(false);
const error = ref('');
const keyInputRef = ref(null);

watch(showAdd, async (open) => {
  if (!open) return;
  key.value = '';
  error.value = '';
  await nextTick();
  setTimeout(() => keyInputRef.value?.focus(), 30);
});

function validate() {
  if (!key.value.trim()) return 'Field Name is required.';
  if (!/^[A-Za-z][A-Za-z0-9]*$/.test(key.value.trim())) {
    return 'Field Name must start with a letter and contain only letters/digits.';
  }
  return '';
}

// ----- Drag-and-drop to the editor -----
function buildDragGhost(k) {
  const ghost = document.createElement('div');
  ghost.className = 'ts-drag-ghost';
  ghost.textContent = `« ${k} »`;
  document.body.appendChild(ghost);
  return ghost;
}

function handleChipDragStart(e, k) {
  if (!e.dataTransfer) return;
  try {
    e.dataTransfer.setData(MERGE_FIELD_MIME, k);
    e.dataTransfer.setData('text/plain', k);
    e.dataTransfer.setData(
      MERGE_FIELD_PAYLOAD_MIME,
      JSON.stringify({ source: 'merge-fields-panel', key: k }),
    );
    e.dataTransfer.effectAllowed = 'copy';
    const ghost = buildDragGhost(k);
    try {
      e.dataTransfer.setDragImage(ghost, ghost.offsetWidth / 2, ghost.offsetHeight / 2);
    } catch { /* ignore */ }
    e.currentTarget.__tsDragGhost = ghost;
  } catch { /* ignore */ }
}

function handleChipDragEnd(e) {
  const ghost = e?.currentTarget?.__tsDragGhost;
  if (ghost && ghost.parentNode) ghost.parentNode.removeChild(ghost);
  if (e?.currentTarget) e.currentTarget.__tsDragGhost = null;
}

async function handleSubmit(e) {
  e?.preventDefault?.();
  const v = validate();
  if (v) { error.value = v; return; }
  error.value = '';
  saving.value = true;
  try {
    const result = await addCommonMergeField({ key: key.value.trim() });
    emit('custom-field-added', { key: result.key, field: result.field });
    showAdd.value = false;
  } catch (err) {
    error.value = err.message || String(err);
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <aside class="ts-fields-panel">
    <header class="ts-fields-head">
      <h3>Merge Fields</h3>
      <p class="ts-fields-subtitle">Click to insert at the caret, or drag into the document.</p>
    </header>

    <div class="ts-fields-groups">
      <ul class="ts-field-chip-list">
        <li
          v-for="f in fields"
          :key="f.key"
          class="ts-field-chip-li"
          draggable="true"
          @dragstart="handleChipDragStart($event, f.key)"
          @dragend="handleChipDragEnd"
        >
          <button
            type="button"
            class="ts-field-chip"
            :title="`Insert ${f.key} — drag to drop into document`"
            @click="emit('insert-field', f.key)"
          >
            <span class="ts-field-chip-label">{{ f.key }}</span>
          </button>
        </li>
      </ul>
      <p v-if="fields.length === 0" class="ts-empty">
        No merge fields yet. Use the <strong>Add Field</strong> button below to add one.
      </p>
    </div>

    <footer class="ts-fields-foot">
    </footer>

    <!-- Add-Field dialog (native HTML modal). -->
    <div
      v-if="showAdd"
      class="ts-add-field-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="ts-add-field-title"
      @click="e => { if (e.target === e.currentTarget && !saving) showAdd = false }"
    >
      <div class="ts-add-field-dialog" @click.stop>
        <header class="ts-add-field-head">
          <h3 id="ts-add-field-title">Add Merge Field</h3>
          <button
            type="button"
            class="ts-add-field-close"
            aria-label="Close"
            :disabled="saving"
            @click="showAdd = false"
          >×</button>
        </header>

        <form class="ts-add-field-form" @submit.prevent="handleSubmit">
          <label class="ts-add-field-label" for="ts-af-key">
            Field Name
            <input
              ref="keyInputRef"
              id="ts-af-key"
              type="text"
              class="ts-input"
              placeholder="e.g. DonorEmail"
              v-model="key"
              :disabled="saving"
              pattern="^[A-Za-z][A-Za-z0-9]*$"
              required
            />
            <small class="ts-hint">CamelCase, letters/digits only, leading letter.</small>
          </label>

          <p v-if="error" class="ts-add-field-error">{{ error }}</p>

          <footer class="ts-add-field-actions">
            <button
              type="button"
              class="ts-modal-flat-btn"
              :disabled="saving"
              @click="showAdd = false"
            >Cancel</button>
            <button
              type="submit"
              class="ts-modal-primary-btn"
              :disabled="saving"
            >{{ saving ? 'Saving…' : 'Add Field' }}</button>
          </footer>
        </form>
      </div>
    </div>
  </aside>
</template>