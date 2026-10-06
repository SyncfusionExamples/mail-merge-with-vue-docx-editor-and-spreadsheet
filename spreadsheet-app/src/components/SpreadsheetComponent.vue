<template>
  <div class="wrapper">
    <ejs-spreadsheet
      ref="spreadsheet"
      :openUrl="openUrl"
      :saveUrl="saveUrl"
      :created="created"
      :fileMenuBeforeOpen="fileMenuBeforeOpen"
      :fileMenuItemSelect="fileMenuItemSelect"
    ></ejs-spreadsheet>
  </div>
</template>

<script>
import { SpreadsheetComponent as EjsSpreadsheet } from "@syncfusion/ej2-vue-spreadsheet";

export default {
  components: {
    "ejs-spreadsheet": EjsSpreadsheet,
  },
  data: () => ({
    openUrl: "http://127.0.0.1:5000/Open",
    saveUrl: "http://127.0.0.1:5000/Save",
    spreadsheet: null,
  }),
  methods: {
    created() {
      var spreadsheet = this.$refs.spreadsheet;
      // Add a custom "Save" item.
      spreadsheet.addFileMenuItems(
          [{
            text: "Save",
            iconCss: "e-save-as e-icons",
          }],
          "Print",
          false
        );
    },
    fileMenuBeforeOpen(){
      var spreadsheet = this.$refs.spreadsheet;
      // Hide the default "Open" and "Save As" items as soon as the ribbon is built.
      spreadsheet.hideFileMenuItems(["Open", "Save As", "New", "Print"], true);
    },
    fileMenuItemSelect(args) {
      // Handle the custom "Save" menu item click via the fileMenuItemSelect event.
      if (args && args.item && args.item.text === "Save") {
        console.log("hello");
      }
    }
  },
};
</script>

