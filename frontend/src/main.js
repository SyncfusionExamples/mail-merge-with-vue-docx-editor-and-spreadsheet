import { createApp } from 'vue'

import '@syncfusion/ej2-base/styles/tailwind3.css';
import '@syncfusion/ej2-buttons/styles/tailwind3.css';
import '@syncfusion/ej2-popups/styles/tailwind3.css';
import '@syncfusion/ej2-inputs/styles/tailwind3.css';
import '@syncfusion/ej2-lists/styles/tailwind3.css';
import '@syncfusion/ej2-navigations/styles/tailwind3.css';
import '@syncfusion/ej2-splitbuttons/styles/tailwind3.css';
import '@syncfusion/ej2-dropdowns/styles/tailwind3.css';
import '@syncfusion/ej2-ribbon/styles/tailwind3.css';
import '@syncfusion/ej2-documenteditor/styles/tailwind3.css';
// Spreadsheet (mounted in a modal dialog from App.vue when the user
// clicks "Edit Excel"). Requires the matching ej2-spreadsheet base +
// ribbon CSS so the toolbar renders correctly.


import './index.css'
import App from './App.vue'

createApp(App).mount('#app')