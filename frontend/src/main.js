import { createApp } from 'vue'
import { registerLicense } from '@syncfusion/ej2-base'
import { getApiPath } from './utils/apiPaths.js'
// Spreadsheet (mounted in a modal dialog from App.vue when the user
// clicks "Edit Excel"). Requires the matching ej2-spreadsheet base +
// ribbon CSS so the toolbar renders correctly.

import './index.css'
import App from './App.vue'

// Fetch the license key from the backend (Azure app setting SYNCFUSION_LICENSE_KEY)
// before mounting, so the components are licensed when they render.
// Includes base path for multi-app service deployments.
async function bootstrap() {
  try {
    const res = await fetch(getApiPath('/LicenseKey'))
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