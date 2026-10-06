<template>
  <div class="app-container">
    <header class="app-header">
      <h1 class="app-title">Spreadsheet Editor</h1>
      <div class="button-group">
        <button
          v-if="!showSpreadsheet"
          @click="openSpreadsheet"
          class="btn btn-primary"
        >
          Edit with Spreadsheet
        </button>
      </div>
    </header>

    <ejs-dialog
      ref="sheetDialog"
      :visible="showSpreadsheet"
      :showCloseIcon="true"
      :closeOnEscape="true"
      :width="'90%'"
      :height="'80%'"
      :target="dialogTarget"
      :allowDragging="true"
      :enableResize="true"
      @close="onDialogClose"
    >
      <div class="dialog-content">
        <SpreadsheetComponent />
      </div>
    </ejs-dialog>

    <div v-if="!showSpreadsheet" class="placeholder">
      <p>Click <strong>Edit with Spreadsheet</strong> to start editing.</p>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue';
import { DialogComponent as EjsDialog } from '@syncfusion/ej2-vue-popups';
import SpreadsheetComponent from './SpreadsheetComponent.vue';

const showSpreadsheet = ref(false);
const sheetDialog = ref(null);
const dialogTarget = '.app-container';

const openSpreadsheet = () => {
  showSpreadsheet.value = true;
};

const onDialogClose = () => {
  showSpreadsheet.value = false;
};
</script>