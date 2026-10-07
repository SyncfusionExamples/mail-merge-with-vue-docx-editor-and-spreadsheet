import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  base: './',
  plugins: [vue()],
  server: { proxy: { '/Open': 'http://127.0.0.1:5000', '/Save': 'http://127.0.0.1:5000', '/OpenRentRoll': 'http://127.0.0.1:5000',
    '/SaveRentRoll': 'http://127.0.0.1:5000', '/LicenseKey': 'http://127.0.0.1:5000' } }
})
