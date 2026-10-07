<script setup>
// SmartAIAssistPane: chat-style AI view docked on the LEFT of the
// DocumentEditor — same structure as Syncfusion's Smart AI Assist demo:
//   - conversation list (user + AI bubbles),
//   - suggestion chips over the input box,
//   - input box + send button at the bottom.
// Selection-aware: if the user has text selected in the document, intent
// actions (Rephrase / Grammar / Translate / Summarize) act on the
// selection; otherwise the input itself is the Generate prompt.
// Every AI reply gets "Insert at caret" / "Replace selection" actions.
import { nextTick, onMounted, ref } from 'vue';
import { getAzureChatAIRequest } from '../ai/ai-models.js';
import {
  AiIntent,
  SUGGESTIONS,
  buildPrompt,
  cleanAiOutput,
  htmlToPlain,
} from '../ai/prompts.js';
import { systemClipboard } from '../utils/studioStorage.js';

// Parent (App.vue) exposes the editor accessors via props.
const props = defineProps({
  getEditor: { type: Function, required: true },
  getSelectionText: { type: Function, required: true },
  insertText: { type: Function, required: true },
});

// Max characters we hand to the AI from the live document. The Syncfusion
// DocumentEditor can return arbitrarily long text; we cap it so a single
// click on "Summarize this document" doesn't blow past the model's
// context window or burn through Azure OpenAI quota.
const MAX_DOC_CHARS = 12_000;

function truncate(text, max = MAX_DOC_CHARS) {
  if (!text) return '';
  return text.length > max ? text.slice(0, max) + '…' : text;
}

// Read the entire document body as plain text. Used as the implicit
// "selection" when the user clicks a document-level chip (Summarize /
// Rephrase / Fix grammar) without first selecting anything.
//
// Syncfusion's DocumentEditor API for the whole-document text is
// `saveAsBlob(format)` which returns a Blob of the serialized
// document; for plain text pass 'Txt'. The blob is then read back as
// a UTF-8 string.
async function fullDocumentText() {
  try {
    const de = props.getEditor();
    if (!de || typeof de.saveAsBlob !== 'function') return '';
    const blob = await de.saveAsBlob('Txt');
    if (!blob) return '';
    // Read the blob as text and trim. We use FileReader for the
    // broadest browser support — `await blob.text()` would also work
    // in modern browsers but FileReader is universally available.
    const text = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = () => reject(reader.error || new Error('FileReader failed'));
      reader.readAsText(blob);
    });
    return String(text || '').trim();
  } catch (err) {
    // eslint-disable-next-line no-console
    console.warn('fullDocumentText failed:', err);
    return '';
  }
}

const messages = ref([]);  // { role: 'user' | 'ai', text, plain, intent }
const input = ref('');
const isThinking = ref(false);
const convoRef = ref(null);

const INTENT_ACTIONS = [
  { intent: AiIntent.Rephrase, label: 'Rephrase selection' },
  { intent: AiIntent.Grammar, label: 'Fix grammar of selection' },
  { intent: AiIntent.Translate, label: 'Translate selection' },
  { intent: AiIntent.Summarize, label: 'Summarize selection' },
];

onMounted(() => {
  messages.value = [
    {
      role: 'ai',
      text: 'Hi! I can <strong>generate</strong> content, or <strong>rephrase</strong>, <strong>translate</strong>, <strong>grammar-check</strong>, and <strong>summarize</strong> selected text. Pick a suggestion below or type a prompt.',
      plain: '',
      intent: null,
    },
  ];
});

async function scrollConvo() {
  await nextTick();
  const el = convoRef.value;
  if (el) el.scrollTop = el.scrollHeight;
}

async function pushMsg(role, text, plain = '', intent = null) {
  messages.value.push({ role, text, plain, intent });
  await scrollConvo();
}

function selectionText() {
  try { return (props.getSelectionText() || '').trim(); } catch { return ''; }
}

// Map a user prompt to an intent: if a selection exists and the prompt
// (or chip) mentions refine-actions, act on the selection; otherwise the
// prompt is a plain Generate request.
function detectIntent(prompt) {
  const p = (prompt || '').toLowerCase();
  const sel = selectionText();
  if (sel && /rephra|rewrite|para/.test(p)) return AiIntent.Rephrase;
  if (sel && /grammar|fix|correct|spelling/.test(p)) return AiIntent.Grammar;
  if (sel && /translate/.test(p)) return AiIntent.Translate;
  if (sel && /summari|tl;?dr/.test(p)) return AiIntent.Summarize;
  return AiIntent.Generate;
}

// Document-level chip clicks (e.g. "Summarize this document") should
// run the matching intent on the whole document, not on the (empty)
// selection. Returns one of AiIntent.* or null when the prompt isn't
// a recognized document-level action.
function detectDocumentLevelIntent(prompt) {
  const p = (prompt || '').toLowerCase();
  if (/summari|tl;?dr/.test(p)) return AiIntent.Summarize;
  if (/rephra|rewrite|para/.test(p)) return AiIntent.Rephrase;
  if (/grammar|fix|correct|spelling/.test(p)) return AiIntent.Grammar;
  return null;
}

async function ask(prompt, forcedIntent = null) {
  const cleanPrompt = String(prompt || '').trim();
  if (!cleanPrompt && !forcedIntent) return;
  if (isThinking.value) return;

  const sel = selectionText();
  // Resolve the intent in priority order:
  //   1) forcedIntent from a chip click (we know what the user wants)
  //   2) explicit selection-aware detection (keyword + selection present)
  //   3) document-level detection (chip clicked but no selection) → fetch full doc
  //   4) Generate
  let intent = forcedIntent
    || (sel ? detectIntent(cleanPrompt) : null)
    || detectDocumentLevelIntent(cleanPrompt)
    || AiIntent.Generate;

  let source;
  if (intent === AiIntent.Generate) {
    source = cleanPrompt;
  } else {
    // For refine actions we prefer the current selection, falling back to
    // the whole document when the user clicked a document-level chip.
    // fullDocumentText() is async because Syncfusion's getText /
    // saveAsBlob returns a Promise / Blob.
    let fullDoc = '';
    if (!sel) {
      isThinking.value = true;
      await pushMsg('ai', '<em>Reading the full document…</em>', '', 'thinking');
      fullDoc = truncate(await fullDocumentText());
      // Pop the "Reading…" placeholder — we re-push a Thinking bubble
      // below so the chat always shows the same loading state.
      messages.value.pop();
    }
    source = sel || fullDoc;
    if (!source || source.length < 3) {
      await pushMsg('ai', 'The document is empty or has no readable text. Type a prompt or add content first.');
      return;
    }
  }

  // Show what the user asked. For selection intents, label with the
  // (possibly truncated) source so the chat makes the action obvious.
  const userLabel = intent === AiIntent.Generate
    ? cleanPrompt
    : `${cleanPrompt || 'Act on selection:'} <em>“${source.slice(0, 140)}${source.length > 140 ? '…' : ''}”</em>`;
  await pushMsg('user', userLabel);

  isThinking.value = true;
  await pushMsg('ai', '<em>Thinking…</em>', '', 'thinking');
  try {
    const options = buildPrompt(intent, source, {
      userHint: intent === AiIntent.Generate ? cleanPrompt : '',
    });
    const out = await getAzureChatAIRequest(options);
    messages.value.pop(); // remove Thinking bubble

    const clean = cleanAiOutput(out);
    const plain = htmlToPlain(clean);
    await pushMsg('ai', clean, plain, intent);
  } catch (err) {
    messages.value.pop();
    // eslint-disable-next-line no-console
    console.error('AI request failed:', err);
    await pushMsg('ai', `AI error: ${err?.message || err}`);
  } finally {
    isThinking.value = false;
    input.value = '';
  }
}

function onSend() {
  const value = input.value.trim();
  if (!value) return;
  ask(value);
}

// Insert an AI reply into the document. For Generate the text lands at
// the caret; for selection intents it REPLACES the selected text.
// For document-level intents (Summarize / Rephrase / Fix grammar
// fired without a real selection) we just insert at the caret.
//
// Formatting is preserved end-to-end: we POST the AI's HTML reply to
// the server's /SystemClipboard endpoint, get SFDT back, and use
// `editor.editor.paste(sfdtString)` to insert it. This is the same
// code path the AI rewrite dialog uses and is the Syncfusion-
// recommended way to insert pre-formatted content (editor.insertText
// drops every style). If the server paste fails for any reason we
// fall back to plain-text insertText so the user never sees an error.
async function insertReply(msg) {
  if (!msg.plain) return;
  const de = props.getEditor();
  if (!de) return;
  try {
    de.focusIn();
    const replaceSelection = !!(msg.intent && msg.intent !== AiIntent.Generate && selectionText());
    if (replaceSelection) {
      if (de.editor && typeof de.editor.delete === 'function') {
        de.editor.delete();
      }
    }
    // Prefer the AI's HTML output (msg.text, which has bold/italic/
    // lists/headings) over the plain-text fallback. Wrap it in a
    // minimal HTML envelope so the Syncfusion LoadString parser
    // recognises it as a document fragment even if the model
    // returned a partial snippet.
    const rawHtml = (msg.text || '').trim();
    const htmlEnvelope = rawHtml
      ? (/^<[a-z][\s\S]*>/i.test(rawHtml) ? rawHtml : `<p>${rawHtml}</p>`)
      : `<p>${(msg.plain || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')}</p>`;
    let sfdt = '';
    try {
      sfdt = await systemClipboard({ content: htmlEnvelope, type: 'html' });
    } catch (clipErr) {
      // eslint-disable-next-line no-console
      console.warn('[SmartAIAssistPane] SystemClipboard failed, falling back to plain text:', clipErr);
      sfdt = '';
    }
    if (sfdt) {
      if (de.editor && typeof de.editor.paste === 'function') {
        de.editor.paste(sfdt);
      } else if (de.paste) {
        de.paste(sfdt);
      } else {
        // No paste() available — fall back to plain text.
        props.insertText(msg.plain);
      }
    } else {
      // Server returned empty SFDT (bad HTML, parser error, etc.) —
      // fall back to the plain-text insert so the user still sees
      // the AI's reply land in the document.
      props.insertText(msg.plain);
    }
  } catch (err) {
    // eslint-disable-next-line no-console
    console.error('Insert failed:', err);
  }
}

// Copy an AI reply to the system clipboard. We write BOTH the HTML
// (so pasting into Word / Gmail / a rich text editor preserves the
// AI's formatting) and the plain text (so pasting into a plain-text
// context, or reading the clipboard from script, gets the readable
// version). When the rich ClipboardItem API isn't available
// (insecure context, older browser) we fall back to copying the
// plain text. This mirrors the React reference sample's
// responseToolbarSettings.itemClicked "copy" handler.
async function copyReply(msg) {
  if (!msg || (!msg.text && !msg.plain)) return;
  const html = (msg.text || '').trim();
  const plain = (msg.plain || '').trim();
  let copied = false;
  try {
    if (navigator.clipboard && typeof window.ClipboardItem === 'function') {
      // Build the two blobs the browser hands off to the OS
      // clipboard. The MIME type "text/html" is what tells rich
      // text targets (Word, Outlook, Gmail compose, etc.) to
      // preserve formatting; "text/plain" is the universal fallback.
      const parts = [];
      if (html)  parts.push(['text/html',  new Blob([html],  { type: 'text/html'  })]);
      if (plain) parts.push(['text/plain', new Blob([plain], { type: 'text/plain' })]);
      if (parts.length) {
        await navigator.clipboard.write(parts.map(([type, blob]) => ({ [type]: blob })).reduce((a, b) => Object.assign(a, b), {}));
        copied = true;
      }
    }
  } catch (err) {
    // eslint-disable-next-line no-console
    console.warn('[SmartAIAssistPane] rich clipboard write failed, falling back to text:', err);
  }
  if (!copied && navigator.clipboard && navigator.clipboard.writeText) {
    try {
      await navigator.clipboard.writeText(plain || html);
      copied = true;
    } catch (err) {
      // eslint-disable-next-line no-console
      console.warn('[SmartAIAssistPane] clipboard.writeText also failed:', err);
    }
  }
  if (!copied) {
    // Last-resort fallback: legacy execCommand for very old browsers.
    try {
      const ta = document.createElement('textarea');
      ta.value = plain || html;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      copied = true;
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error('[SmartAIAssistPane] execCommand copy failed:', err);
    }
  }
  // Give the user a tiny visual hint that the copy succeeded.
  if (copied) {
    msg.copied = true;
    setTimeout(() => { msg.copied = false; }, 1500);
  }
}
</script>

<template>
  <aside class="ts-ai-panel">
    <header class="ts-ai-head">
      <h3>Smart AI Assist</h3>
      <p class="ts-ai-subtitle">Generate content or refine the selected text.</p>
    </header>

    <!-- Conversation: user bubbles on the right, AI on the left. -->
    <div ref="convoRef" class="ts-ai-convo">
      <div
        v-for="(m, i) in messages"
        :key="i"
        class="ts-ai-msg"
        :class="m.role === 'user' ? 'ts-ai-msg-user' : 'ts-ai-msg-ai'"
      >
        <span class="ts-ai-msg-role">{{ m.role === 'user' ? 'You' : 'AI' }}</span>
        <div class="ts-ai-msg-body" v-html="m.text" />
        <footer v-if="m.role === 'ai' && m.plain" class="ts-ai-msg-actions">
          <button
            type="button"
            :title="m.intent === AiIntent.Generate || (m.intent && !selectionText()) ? 'Insert at caret' : 'Replace selection'"
            @click="insertReply(m)"
          >{{ m.intent === AiIntent.Generate || (m.intent && !selectionText()) ? '+' : 'Replace selection' }}</button>
          <button
            type="button"
            class="ts-ai-copy-btn"
            :title="m.copied ? 'Copied!' : 'Copy reply to clipboard'"
            :aria-label="m.copied ? 'Copied' : 'Copy reply to clipboard'"
            @click="copyReply(m)"
          >
            <span
              v-if="m.copied"
              class="e-icons e-check"
              aria-hidden="true"
            />
            <span
              v-else
              class="e-icons e-copy"
              aria-hidden="true"
            />
          </button>
        </footer>
      </div>
    </div>

    <!-- Suggestion chips + input box (same structure as the Smart AI Assist demo). -->
    <div class="ts-ai-input-area">
      <div class="ts-ai-chips">
        <template v-if="selectionText()">
          <button
            v-for="a in INTENT_ACTIONS"
            :key="a.intent"
            type="button"
            class="ts-ai-chip"
            :disabled="isThinking"
            @click="ask(a.label, a.intent)"
          >{{ a.label }}</button>
        </template>
        <template v-else>
          <button
            v-for="s in SUGGESTIONS"
            :key="s"
            type="button"
            class="ts-ai-chip"
            :disabled="isThinking"
            @click="ask(s)"
          >{{ s }}</button>
        </template>
      </div>

      <div class="ts-ai-input-row">
        <textarea
          class="ts-ai-input"
          rows="2"
          placeholder="Type a prompt… (Enter to send)"
          v-model="input"
          :disabled="isThinking"
          @keydown.enter.prevent="onSend"
        />
        <button
          type="button"
          class="ts-ai-send"
          :disabled="isThinking || !input.trim()"
          title="Send"
          aria-label="Send"
          @click="onSend"
        >
          <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
            <path fill="currentColor" d="M2.01 21 23 12 2.01 3 2 10l15 2-15 2z" />
          </svg>
        </button>
      </div>
    </div>
  </aside>
</template>