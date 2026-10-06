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

// Parent (App.vue) exposes the editor accessors via props.
const props = defineProps({
  getEditor: { type: Function, required: true },
  getSelectionText: { type: Function, required: true },
  insertText: { type: Function, required: true },
});

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

async function ask(prompt, forcedIntent = null) {
  const cleanPrompt = String(prompt || '').trim();
  if (!cleanPrompt && !forcedIntent) return;
  if (isThinking.value) return;

  const intent = forcedIntent || detectIntent(cleanPrompt);
  const sel = selectionText();

  // Show what the user asked (for selection intents, show the selection).
  const userLabel = intent === AiIntent.Generate
    ? cleanPrompt
    : `${cleanPrompt || 'Act on selection:'} ${sel ? `<em>“${sel.slice(0, 140)}${sel.length > 140 ? '…' : ''}”</em>` : '(no text selected)'}`;
  await pushMsg('user', userLabel);

  isThinking.value = true;
  await pushMsg('ai', '<em>Thinking…</em>', '', 'thinking');
  try {
    let source;
    if (intent === AiIntent.Generate) {
      source = cleanPrompt;
    } else {
      source = sel;
      if (!source || source.length < 3) {
        messages.value.pop(); // remove Thinking bubble
        await pushMsg('ai', 'Select some text in the document first, then run this action.');
        return;
      }
    }

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
function insertReply(msg) {
  if (!msg.plain) return;
  const de = props.getEditor();
  if (!de) return;
  try {
    de.focusIn();
    if (msg.intent && msg.intent !== AiIntent.Generate) {
      const sel = selectionText();
      if (sel && de.editor) de.editor.delete();
    }
    props.insertText(msg.plain);
  } catch (err) {
    // eslint-disable-next-line no-console
    console.error('Insert failed:', err);
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
            @click="insertReply(m)"
          >{{ m.intent === AiIntent.Generate ? 'Insert at caret' : 'Replace selection' }}</button>
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