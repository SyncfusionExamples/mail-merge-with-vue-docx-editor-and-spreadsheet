// AI request helper — mirrors the react-docx-editor-with-ai sample's
// ai-models.ts. All AI prompts are routed through the ASP.NET Core Web API
// (POST /api/DocumentEditor/Process) so Azure OpenAI credentials stay on
// the server. The endpoint accepts an { messages, model } body and returns
// { Text } with the generated content.

import { AI_API_BASE } from '../data/sampleTemplates.js';

export async function getAzureChatAIRequest(options) {
  try {
    const response = await fetch(`${AI_API_BASE}/Process`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(options),
    });
    if (!response.ok) {
      // Surface the server's actual error text (the AIController returns
      // { error } on 500s — e.g. Azure config problems) instead of a
      // generic status code so the chat pane can show the real cause.
      let detail = '';
      try {
        const body = await response.json();
        detail = body.error || JSON.stringify(body);
      } catch {
        try { detail = await response.text(); } catch { /* ignore */ }
      }
      throw new Error(`API Error ${response.status}: ${String(detail).slice(0, 300)}`);
    }
    const result = await response.json();
    // The server returns { Text }. Accept a lowercase `text` too, and a
    // bare string for legacy/alternate servers.
    const text = result?.Text ?? result?.text ?? null;
    if (!text) {
      throw new Error('The AI endpoint returned an empty response body.');
    }
    return text;
  } catch (err) {
    // eslint-disable-next-line no-console
    console.error('[AI] request failed:', err);
    throw err;
  }
}