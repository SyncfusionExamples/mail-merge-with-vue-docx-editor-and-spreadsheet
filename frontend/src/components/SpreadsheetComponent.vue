<template>
  <div class="ts-spreadsheet-wrapper">
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
  name: "SpreadsheetComponent",
  components: {
    "ejs-spreadsheet": EjsSpreadsheet,
  },
  data: () => ({
    openUrl: "Open",
    saveUrl: "Save",
    spreadsheet: null,
  }),
  methods: {
    created() {
      var spreadsheet = this.$refs.spreadsheet;
      // Add a custom "Save" item.
      spreadsheet.addFileMenuItems(
        [
          {
            text: "Save",
            iconCss: "e-save-as e-icons",
          },
        ],
        "Print",
        false
      );

      // When the spreadsheet finishes its initial render, fetch the
      // rentRollDetails.xlsx from the Python service and open it.
      this.loadRentRoll(spreadsheet);
    },
    loadRentRoll(spreadsheet) {
      // Call the new backend endpoint that returns the JSON produced by
      // SpreadsheetEditor.Open(byte[]) for the file shipped in the Files folder.
      fetch("OpenRentRoll", { method: "GET" })
        .then((response) => {
          if (!response.ok) {
            throw new Error(`Failed to load rent roll: ${response.status}`);
          }
          return response.blob();
        })
        .then((fileBlob) => {
          // Read the blob as text and parse it to JSON, then hand it to
          // the spreadsheet's openFromJson() method.
          fileBlob.text().then((jsonText) => {
            const workbookJson = JSON.parse(jsonText);
            spreadsheet.openFromJson({ file: workbookJson });
          });
        })
        .catch((err) => {
          console.error("OpenRentRoll failed:", err);
        });
    },
    fileMenuBeforeOpen() {
      var spreadsheet = this.$refs.spreadsheet;
      // Hide the default "Open" and "Save As" items as soon as the ribbon is built.
      spreadsheet.hideFileMenuItems(["Open", "Save As", "New", "Print"], true);
    },
    fileMenuItemSelect(args) {
      // Handle the custom "Save" menu item click via the fileMenuItemSelect event.
      if (args && args.item && args.item.text === "Save") {
        this.saveRentRoll();
      }
    },
    saveRentRoll() {
      var spreadsheet = this.$refs.spreadsheet;

      // Use saveAsJson to get the proper workbook JSON format
      spreadsheet.saveAsJson({ ignoreValidation: true }).then((response) => {
        var formData = new FormData();
        formData.append(
          "JSONData",
          JSON.stringify(response.jsonObject.Workbook)
        );
        // The save target is the SHARED Excel file the Spreadsheet
        // and the DocumentEditor mail-merge both edit. The server
        // ignores the fileName value and writes the canonical
        // shared file (Files/Data/Property Portfolio Data.xlsx) in place.
        formData.append("fileName", "Property Portfolio Data");
        formData.append("saveType", "Xlsx");
        formData.append(
          "pdfLayoutSettings",
          JSON.stringify({ fitSheetOnOnePage: false, orientation: "Portrait" })
        );

        // Call the SaveRentRoll endpoint that replaces the existing file
        fetch("SaveRentRoll", {
          method: "POST",
          body: formData,
        })
          .then((response) => {
            if (!response.ok) {
              throw new Error(`Failed to save shared data file: ${response.status}`);
            }
            return response.json();
          })
          .then((result) => {
            console.log("Shared data file saved successfully:", result);
          })
          .catch((err) => {
            console.error("SaveRentRoll failed:", err);
            alert("Error saving shared data file: " + err.message);
          });
      }).catch((err) => {
        console.error("Failed to serialize spreadsheet:", err);
        alert("Error preparing shared data file for save: " + err.message);
      });
    },
  },
};
</script>

<style>
/* The spreadsheet must be allowed to fill its host container — Syncfusion
   measures the parent. We give it an explicit, responsive size and reset
   any extra margin that would push the toolbar off-screen. */
.ts-spreadsheet-wrapper {
  width: 100%;
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.ts-spreadsheet-wrapper .e-spreadsheet {
  width: 100% !important;
  height: 100% !important;
  flex: 1 1 auto;
}
</style>