import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Talks directly to the ASP.NET Core service (same backend as the full
// samples): DocumentEditor import/save/mail-merge. No template list UI —
// the homepage IS the editor.
export default defineConfig({
  base: process.env.VITE_APP_BASE_PATH || '/vue-spreadsheet-docx-mail-merge/',
  plugins: [vue()],
  server: { proxy: { '/Open': 'http://127.0.0.1:5000', '/Save': 'http://127.0.0.1:5000', '/OpenRentRoll': 'http://127.0.0.1:5000',
    '/SaveRentRoll': 'http://127.0.0.1:5000', '/LicenseKey': 'http://127.0.0.1:5000',
    '/api/DocumentEditor/MailMerge': 'http://127.0.0.1:5000',
    '/api/DocumentEditor/Import': 'http://127.0.0.1:5000',
    '/api/DocumentEditor/ImportFileURL': 'http://127.0.0.1:5000',
    '/api/DocumentEditor/SystemClipboard': 'http://127.0.0.1:5000',
    '/api/DocumentEditor/RestrictEditing': 'http://127.0.0.1:5000',
    '/api/DocumentEditor/Save': 'http://127.0.0.1:5000',
    '/api/DocumentEditor/Export': 'http://127.0.0.1:5000',
    '/api/DocumentEditor/Process': 'http://127.0.0.1:5000' } }
})