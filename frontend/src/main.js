import { createApp } from 'vue'
// Spreadsheet (mounted in a modal dialog from App.vue when the user
// clicks "Edit Excel"). Requires the matching ej2-spreadsheet base +
// ribbon CSS so the toolbar renders correctly.

import './index.css'
import App from './App.vue'

createApp(App).mount('#app')