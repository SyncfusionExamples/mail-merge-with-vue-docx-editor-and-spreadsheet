import { createApp } from 'vue'
import { registerLicense } from '@syncfusion/ej2-base'
// Spreadsheet (mounted in a modal dialog from App.vue when the user
// clicks "Edit Excel"). Requires the matching ej2-spreadsheet base +
// ribbon CSS so the toolbar renders correctly.

registerLicense('Add Syncfusion DOCX Editor; Spreadsheet license');

import './index.css'
import App from './App.vue'

createApp(App).mount('#app')