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
      fetch("http://127.0.0.1:5000/OpenRentRoll", { method: "GET" })
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
          'JSONData',
          JSON.stringify(response.jsonObject.Workbook)
        );
        formData.append('fileName', 'rentRollDetails');
        formData.append('saveType', 'Xlsx');
        formData.append('pdfLayoutSettings', JSON.stringify({ fitSheetOnOnePage: false, orientation: 'Portrait' }));
        
        // Call the SaveRentRoll endpoint that replaces the existing file
        fetch("http://127.0.0.1:5000/SaveRentRoll", {
          method: 'POST',
          body: formData
        })
          .then((response) => {
            if (!response.ok) {
              throw new Error(`Failed to save rent roll: ${response.status}`);
            }
            return response.json();
          })
          .then((result) => {
            console.log("Rent roll saved successfully:", result);
            alert("Rent roll saved successfully!");
          })
          .catch((err) => {
            console.error("SaveRentRoll failed:", err);
            alert("Error saving rent roll: " + err.message);
          });
      }).catch((err) => {
        console.error("Failed to serialize spreadsheet:", err);
        alert("Error preparing rent roll for save: " + err.message);
      });
    },
  },
};
</script>

