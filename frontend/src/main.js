import { createApp } from 'vue'
import { registerLicense } from '@syncfusion/ej2-base'
import './style.css'
import App from './App.vue'

// Fetch the license key from the backend (Azure app setting SYNCFUSION_LICENSE_KEY)
// before mounting, so the components are licensed when they render.
// Relative URL keeps it working under a sub-path.
async function bootstrap() {
  try {
    const res = await fetch('LicenseKey')
    if (res.ok) {
      const key = (await res.text()).trim()
      if (key) registerLicense(key)
    }
  } catch (e) {
    console.error('Could not load Syncfusion license key', e)
  }
  createApp(App).mount('#app')
}

bootstrap()
