import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Talks directly to the ASP.NET Core service (same backend as the full
// samples): DocumentEditor import/save/mail-merge. No template list UI —
// the homepage IS the editor.
export default defineConfig({
  base: process.env.VITE_APP_BASE_PATH || '/vue-spreadsheet-docx-mail-merge/',
  plugins: [vue()],
  server: {
    proxy: {
      // All API endpoints are at root paths only.
      // SPA base path is handled by VITE_APP_BASE_PATH (Vite/Vue responsibility).
      // API endpoints are always absolute (starting with /), so they're path-independent.
      '/api/': 'http://127.0.0.1:5000',
      '/Open': 'http://127.0.0.1:5000',
      '/Save': 'http://127.0.0.1:5000',
      '/OpenRentRoll': 'http://127.0.0.1:5000',
      '/SaveRentRoll': 'http://127.0.0.1:5000',
      '/LicenseKey': 'http://127.0.0.1:5000',
      '/Templates/': 'http://127.0.0.1:5000',
      '/Data/': 'http://127.0.0.1:5000',
    }
  }
})