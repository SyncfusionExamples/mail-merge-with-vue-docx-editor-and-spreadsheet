// Smart AI Assist — prompt helpers adapted from the react-docx-editor-with-ai
// sample's buildPrompt(). All prompts go through the ASP.NET Core Web API
// (POST /api/DocumentEditor/Process → Azure OpenAI) so credentials stay
// server-side. Prompts ask for HTML output (no <html>/<head>/<body>) so
// the reply can be previewed and inserted into the document as text.

export const AiIntent = {
  Generate: 'Generate',     // free-text prompt → new content
  QandA:     'QandA',      // question about the document (uses doc as context)
  Rephrase: 'Rephrase',     // acts on the editor selection
  Grammar: 'Grammar',       // acts on the editor selection
  Translate: 'Translate',   // acts on the editor selection
  Summarize: 'Summarize',   // acts on the editor selection
};

// Quick-pick suggestion chips shown in the chat pane. The "Summarize this
// document" chip acts on the whole document; free-text Q&A typed in the
// input box uses the document as context (see buildPrompt + QandA intent).
export const SUGGESTIONS = [
  'Summarize this document',
  'What are the key points in this document?',
  'List the names mentioned in this document',
];

export function buildPrompt(intent, text, { tone = 'Professional', format = 'Paragraph', length = 'Medium', toLang = 'French', userHint = '', regenerate = false, documentContext = '' } = {}) {
  const content = (text || '').trim();
  const doc = (documentContext || '').trim();
  const toneValue = String(tone).toLowerCase();
  const formatValue = String(format).toLowerCase();
  const lengthValue = String(length).toLowerCase();
  const htmlRule = ' Always respond in proper HTML format, excluding <html>, <head> and <body> tags. Do not describe what you are doing; respond with the content only.';
  // When the user clicks "Regenerate" in the AI rewrite dialog we
  // ask the model to produce a *different* rewrite from the previous
  // one — the same prompt verbatim usually returns the same answer.
  const regenHint = regenerate
    ? ' Provide a different rewrite than any previous attempt.'
    : '';

  switch (intent) {
    case AiIntent.Generate:
      return {
        messages: [
          { role: 'system', content: `You are a helpful document assistant. Generate content based on the user's request to reflect a tone of '${toneValue}', formatted in '${formatValue}' style, and maintain a length of '${lengthValue}'.${htmlRule}` },
          { role: 'user', content: content || userHint },
        ],
        model: 'gpt-4',
      };
    case AiIntent.QandA: {
      // Q&A about the document — same pattern as the react-docx-editor-with-ai
      // sample's getDocumentText(): the document text is included as
      // "Context" so the model can answer based on the actual file
      // rather than inventing data. The user question is the second
      // user message so the model can clearly see "context vs. question".
      const contextBlock = doc
        ? `\n\nContext (document text):\n"""${doc}"""`
        : '';
      return {
        messages: [
          { role: 'system', content: `You are a helpful document assistant. Use the provided document context to answer the user's question. If the answer is not in the document, say so explicitly.${htmlRule}` },
          { role: 'user', content: `${content || userHint}${contextBlock}` },
        ],
        model: 'gpt-4',
      };
    }
    case AiIntent.Rephrase:
      return {
        messages: [
          { role: 'system', content: `You are a helpful document assistant. Rephrase the provided text to reflect a tone of '${toneValue}', formatted in '${formatValue}' style, and maintain a length of '${lengthValue}'.${regenHint}${htmlRule}` },
          { role: 'user', content },
        ],
        model: 'gpt-4',
      };
    case AiIntent.Grammar:
      return {
        messages: [
          { role: 'system', content: `You are a helpful document assistant. Analyze the provided text, check for and correct any grammatical errors, and improve clarity.${regenHint}${htmlRule}` },
          { role: 'user', content },
        ],
        model: 'gpt-4',
      };
    case AiIntent.Translate:
      return {
        messages: [
          { role: 'system', content: `You are a helpful document assistant. Translate the provided text into '${toLang}'.${htmlRule}` },
          { role: 'user', content },
        ],
        model: 'gpt-4',
      };
    case AiIntent.Summarize:
      return {
        messages: [
          { role: 'system', content: `You are a helpful document assistant. Summarize the provided text${userHint ? ` focusing on: '${userHint}'` : ''}.${htmlRule}` },
          { role: 'user', content },
        ],
        model: 'gpt-4',
      };
    default:
      return {
        messages: [
          { role: 'system', content: `You are a helpful document assistant.${htmlRule}` },
          { role: 'user', content: content || userHint },
        ],
        model: 'gpt-4',
      };
  }
}

// Strip markdown code fences some models wrap around "HTML" output.
export function cleanAiOutput(out) {
  return String(out || '')
    .replace(/```html\s*/i, '')
    .replace(/```\s*$/, '')
    .trim();
}

// Convert the AI's HTML reply into plain text for editor.insertText().
export function htmlToPlain(html) {
  const div = document.createElement('div');
  div.innerHTML = (html || '')
    .replace(/<\/(p|div|li|h[1-6]|tr)>/gi, '\n')
    .replace(/<br\s*\/?>/gi, '\n');
  const text = div.textContent || '';
  return String(text).replace(/[ \t]+/g, ' ').replace(/\n{3,}/g, '\n\n').trim();
}