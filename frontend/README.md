# Template Studio — Simple (Vue 3 Composition API)

A minimal version of the Template Studio. **No template list UI** — the
homepage is the Syncfusion DocumentEditor itself, and a default `.docx`
is loaded from the Python wrapper service on startup.

## What it does

- Loads `CRE_Appraisal_All_MergeFields.docx` (configurable in
  `src/data/sampleTemplates.js` → `DEFAULT_TEMPLATE_DOCX`) from the
  `<repo>/Files/Templates/` folder into the editor on mount.
- **Save and Publish** — serializes the document to SFDT and POSTs it to
  `api/DocumentEditor/Save`; the same FileName overwrites the same
  `.docx`.
- **Download** — `documentEditor.save()` → local `.docx`.
- **Preview with Data** — mail merge via `api/DocumentEditor/MailMerge`
  (server falls back to `Files/Data/CRE_Appraisal_POC.xlsx` when no
  inline data is provided); the merged result opens in the editor.
- **Merge Fields panel** — built-in catalog + doc MERGEFIELDs + common
  custom fields; click to insert at the caret or drag into the canvas;
  Add Field saves a common-scope custom field via `api/studio/mergefield`.
- **Edit Excel** — opens the bundled `rentRollDetails.xlsx` in the
  Python service's SpreadsheetComponent (in a modal).

## Backend

The Python wrapper (`app.py`) hosts both the spreadsheet service
(`/Open`, `/Save`, `/OpenRentRoll`, `/SaveRentRoll`) and the migrated
document-editor / AI / studio endpoints on a single Flask process
running on port 5000. The original ASP.NET Core service under
`Server-side/` is kept as a reference only and is no longer required
at runtime.

- DocumentEditor service: `http://localhost:5000/api/DocumentEditor/`
- AI Process: `http://localhost:5000/api/DocumentEditor/Process`
- Studio API: `http://localhost:5000/api/studio`
- Template static files: `http://localhost:5000/Templates/<file>.docx`

Start it with `python app.py` (or `gunicorn app:app`) from the repo
root. All runtime configuration lives in `appsettings.json` (with
`appsettings.Development.json` overlaid for local dev) — the same
convention the legacy .NET project used. Process-level environment
variables override file values when you need to inject keys from a
secret manager or container orchestrator:

```json
{
  "Syncfusion":   { "LicenseKey": "<your-syncfusion-key>" },
  "AzureOpenAI":  {
    "Endpoint":      "https://<resource>.openai.azure.com/",
    "ApiKey":        "<your-azure-openai-key>",
    "DeploymentName":"gpt-4o",
    "ApiVersion":    "2024-02-15-preview"
  }
}
```

| appsettings.json key   | Env-var override               | Required? | Purpose                          |
| ---------------------- | ------------------------------ | --------- | -------------------------------- |
| `Syncfusion.LicenseKey`| `SYNCFUSION_LICENSE_KEY`       | Optional  | Removes the eval watermark       |
| `AzureOpenAI.Endpoint` | `AZURE_OPENAI_ENDPOINT`        | Yes (AI)  | Azure OpenAI endpoint            |
| `AzureOpenAI.ApiKey`   | `AZURE_OPENAI_API_KEY`         | Yes (AI)  | Azure OpenAI key                 |
| `AzureOpenAI.DeploymentName` | `AZURE_OPENAI_DEPLOYMENT`  | Yes (AI)  | Deployment name                  |
| `AzureOpenAI.ApiVersion`| `AZURE_OPENAI_API_VERSION`     | Optional  | Defaults to `2024-02-15-preview` |

> The `Server-side/appsettings.json` is reference-only and is never read at runtime.

## Run

```bash
npm install
npm run dev
```

## Structure

```
src/
  main.js                  — entry (Syncfusion tailwind3 CSS themes)
  App.vue                  — homepage = editor; load/save/download/mail-merge
  index.css                — styles
  components/
    MergeFieldsPanel.vue   — merge-field chips + Add Field modal
    MergeFieldsPanelMime.js— drag-and-drop MIME constants
  data/
    sampleTemplates.js     — backend URLs, default docx, MERGE_FIELDS
  utils/
    studioStorage.js       — server API helpers
```