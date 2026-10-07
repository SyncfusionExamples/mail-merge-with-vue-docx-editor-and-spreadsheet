import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Talks directly to the ASP.NET Core service (same backend as the full
// samples): DocumentEditor import/save/mail-merge. No template list UI —
// the homepage IS the editor.
export default defineConfig({
  plugins: [vue()],
})