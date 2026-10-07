<script setup>
// AiRewriteDialog — a Word-style "review changes" dialog shown when an
// AI-rewrite action is requested from the document's right-click
// context menu (Grammar Check, Rephrase, Translate). The dialog shows
// the original selection on the left and the AI-rewritten text on the
// right, with the differences highlighted using a word-level LCS diff
// (ported from the react-docx-editor-with-ai sample). The footer has
// three actions:
//
//   Replace     — applies the rewrite to the document at the original
//                 selection's start position, deleting the old text
//                 and inserting the new text in one operation.
//   Regenerate  — re-runs the AI request with a hint to produce a
//                 different rewrite (no settings dropdown — the task
//                 and tone are fixed by the menu item that opened the
//                 dialog).
//   Cancel      — closes the dialog without touching the document.
//
// v-show keeps the dialog mounted across opens so we avoid the
// Syncfusion double-destroy race (same reason the other dialogs in
// App.vue use v-show).
import { computed, nextTick, ref, watch } from 'vue';
import { DialogComponent } from '@syncfusion/ej2-vue-popups';
import { getAzureChatAIRequest } from '../ai/ai-models.js';
import { AiIntent, buildPrompt, cleanAiOutput } from '../ai/prompts.js';
import { highlightDifferences } from '../utils/textDiff.js';
import { systemClipboard } from '../utils/studioStorage.js';

const props = defineProps({
  visible: { type: Boolean, required: true },
  // One of AiIntent.Rephrase | AiIntent.Grammar | AiIntent.Translate
  intent: { type: String, required: true },
  // The original selection text from the editor (the "From" pane).
  sourceText: { type: String, required: true },
  // The start offset of the original selection in the editor. Captured
  // BEFORE the dialog opens so Replace can put the rewritten text
  // back at the same place, even if the user clicks around in the
  // document while the dialog is open.
  sourceStart: { type: Number, default: null },
  sourceEnd: { type: Number, default: null },
  // Target language (only used when intent === 'Translate').
  toLang: { type: String, default: 'French' },
  // Editor accessors (passed in by App.vue).
  getEditor: { type: Function, required: true },
  focusEditor: { type: Function, required: true },
});

const emit = defineEmits(['update:visible', 'replaced']);

const outHtml = ref('');   // improved text (HTML, with diff highlights)
const inHtml = ref('');    // original text (HTML, with diff highlights)
const isLoading = ref(false);
const errorMsg = ref('');
const lastRaw = ref('');   // last raw (un-highlighted) rewrite — used for re-diffing on Regenerate

const headerText = computed(() => {
  switch (props.intent) {
    case AiIntent.Grammar:   return 'Grammar Check';
    case AiIntent.Rephrase:  return 'Rephrase';
    case AiIntent.Translate: return 'Translate';
    default:                 return 'AI Assistant';
  }
});

const intentLabel = computed(() => {
  switch (props.intent) {
    case AiIntent.Grammar:   return 'Check grammar';
    case AiIntent.Rephrase:  return 'Rephrase';
    case AiIntent.Translate: return 'Translate';
    default:                 return 'Rewrite';
  }
});

function rebuildDiff(rawOutput) {
  const original = `<p>${(props.sourceText || '').trim()}</p>`;
  const { highlightedOriginal, highlightedModified } = highlightDifferences(
    original,
    rawOutput,
  );
  inHtml.value = highlightedOriginal;
  outHtml.value = highlightedModified;
}

// Run the AI and populate both panes. `isRegenerate` swaps the prompt
// for a "vary the previous rewrite" variant.
async function runRewrite(isRegenerate = false) {
  if (!props.sourceText || props.sourceText.trim().length < 3) {
    errorMsg.value = 'Select some text in the document first.';
    return;
  }
  isLoading.value = true;
  errorMsg.value = '';
  try {
    const options = buildPrompt(
      props.intent,
      props.sourceText,
      {
        toLang: props.toLang,
        userHint: isRegenerate ? 'Provide a different rewrite than the previous one.' : '',
        regenerate: isRegenerate,
      },
    );
    let out = await getAzureChatAIRequest(options);
    out = cleanAiOutput(out);
    lastRaw.value = out;
    rebuildDiff(out);
  } catch (err) {
    // eslint-disable-next-line no-console
    console.error('AI rewrite failed:', err);
    errorMsg.value = (err && err.message) ? err.message : String(err);
  } finally {
    isLoading.value = false;
  }
}

// Whenever the dialog opens (becomes visible) kick off a fresh AI
// request with the current source text.
watch(
  () => props.visible,
  async (open) => {
    if (open) {
      errorMsg.value = '';
      outHtml.value = '';
      inHtml.value = '';
      lastRaw.value = '';
      await nextTick();
      runRewrite(false);
    }
  },
  { immediate: false },
);

function closeDialog() {
  emit('update:visible', false);
}

async function onReplace() {
  const de = props.getEditor();
  if (!de) {
    closeDialog();
    return;
  }
  // The AI returns HTML (with bold / italic / lists / headings). We
  // POST it to the server's SystemClipboard endpoint, which converts
  // the HTML to SFDT using Syncfusion.EJ2.WordEditor.LoadString, and
  // then we paste the SFDT into the document with the editor's own
  // `paste(sfdtString)` method. This is the same code path the
  // editor uses for "paste with formatting" when enableLocalPaste is
  // false — it preserves all formatting, unlike `editor.insertText()`
  // which drops every style.
  const html = (lastRaw.value || outHtml.value || '').trim();
  if (!html) {
    closeDialog();
    return;
  }
  try {
    // 1) Delete the original selection (or restore the saved offsets
    //    first if the user has clicked elsewhere in the document).
    const sel = de.selection;
    const currentSel = (sel && typeof sel.text === 'string') ? sel.text.trim() : '';
    if (currentSel && currentSel === (props.sourceText || '').trim()) {
      if (de.editor && typeof de.editor.delete === 'function') {
        de.editor.delete();
      }
    } else if (
      props.sourceStart != null &&
      props.sourceEnd != null &&
      sel &&
      typeof sel.select === 'function'
    ) {
      sel.select(props.sourceStart, props.sourceEnd);
      if (de.editor && typeof de.editor.delete === 'function') {
        de.editor.delete();
      }
    }
    // 2) Ask the server to convert the AI's HTML output to SFDT.
    de.focusIn();
    const sfdt = await systemClipboard({ content: html, type: 'html' });
    if (!sfdt) {
      throw new Error('The server returned an empty SFDT for the AI rewrite.');
    }
    // 3) Paste the SFDT at the cursor. The editor's paste() method
    //    inserts the formatted SFDT exactly the same way the system
    //    clipboard paste does, so all AI-generated formatting
    //    (bold, italic, lists, etc.) is preserved.
    if (de.editor && typeof de.editor.paste === 'function') {
      de.editor.paste(sfdt);
    } else if (de.paste) {
      // Older API surface fallback.
      de.paste(sfdt);
    } else {
      throw new Error('The Document Editor does not support paste().');
    }
    emit('replaced', { intent: props.intent, html });
  } catch (err) {
    // eslint-disable-next-line no-console
    console.error('Replace failed:', err);
    errorMsg.value = (err && err.message) ? err.message : String(err);
    return; // keep the dialog open so the user can see what happened
  }
  closeDialog();
}

async function onRegenerate() {
  await runRewrite(true);
}

// Footer buttons — the order is fixed (Replace / Regenerate / Cancel)
// because the user explicitly asked NOT to add a tone/format dropdown.
const footerButtons = computed(() => [
  {
    click: onReplace,
    buttonModel: {
      content: 'Replace',
      cssClass: 'e-flat e-primary',
      isPrimary: true,
    },
  },
  {
    click: onRegenerate,
    buttonModel: {
      content: 'Regenerate',
      cssClass: 'e-flat',
    },
  },
  {
    click: closeDialog,
    buttonModel: {
      content: 'Cancel',
      cssClass: 'e-flat',
    },
  },
]);
</script>

<template>
  <DialogComponent
    v-show="visible"
    :visible="visible"
    :isModal="true"
    :showCloseIcon="true"
    :closeOnEscape="true"
    :width="'70%'"
    :height="'60%'"
    :target="'.ts-app'"
    :header="headerText"
    :allowDragging="true"
    :animationSettings="{ effect: 'Fade', duration: 200, delay: 0 }"
    cssClass="ts-ai-rewrite-dialog"
    :close="closeDialog"
    :buttons="footerButtons"
  >
    <div class="ts-ai-rewrite-body">
      <p v-if="isLoading" class="ts-ai-rewrite-loading">
        <em>Working on it…</em>
      </p>
      <p v-if="errorMsg" class="ts-ai-rewrite-error">{{ errorMsg }}</p>

      <div class="ts-ai-rewrite-grid">
        <section class="ts-ai-rewrite-pane">
          <header class="ts-ai-rewrite-pane-head">From</header>
          <div class="ts-ai-rewrite-pane-text" v-html="inHtml || '&nbsp;'" />
        </section>
        <section class="ts-ai-rewrite-pane">
          <header class="ts-ai-rewrite-pane-head">To</header>
          <div class="ts-ai-rewrite-pane-text" v-html="outHtml || '&nbsp;'" />
        </section>
      </div>
    </div>
  </DialogComponent>
</template>
