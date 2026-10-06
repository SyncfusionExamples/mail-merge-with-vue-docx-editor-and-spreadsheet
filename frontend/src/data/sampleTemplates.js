// Backend Web API base URL — the Python wrapper (app.py) hosts both the
// spreadsheet (existing) and the migrated document-editor / AI / studio
// endpoints on a single Flask process. The .NET project under
// Server-side/ is kept as a reference only and is no longer required at
// runtime. Everything that needs to call the backend imports from here
// so the host/port lives in one place.

export const DOCUMENT_EDITOR_BASE_URL = 'http://localhost:5000';

// Full service URL the Syncfusion DocumentEditor container needs in its
// `serviceUrl` prop (note trailing slash — that's what the editor expects).
export const DOCUMENT_EDITOR_SERVICE_URL =
  `${DOCUMENT_EDITOR_BASE_URL}/api/DocumentEditor/`;

// The .docx loaded into the homepage editor on startup. Must exist under
// <repo>/Files/Templates/ (served by Flask at /Templates/<file>).
// Change this to whatever document you want the app to open with.
export const DEFAULT_TEMPLATE_DOCX = 'CRE_Appraisal_All_MergeFields.docx';

// ---------------------------------------------------------------------------
// AI backend — the Process endpoint lives on the same Python wrapper
// (/api/DocumentEditor/Process). Credentials are read from environment
// variables (AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY,
// AZURE_OPENAI_DEPLOYMENT). The endpoint returns 500 with instructions
// when the env vars are not set.
// ---------------------------------------------------------------------------
export const AI_API_BASE = 'http://localhost:5000/api/DocumentEditor';

// ---------------------------------------------------------------------------
// Merge field catalog (same static catalog as the full samples). Custom
// fields added via the panel's Add Field dialog are POSTed to the
// server's StudioController (common scope) so they persist.
// ---------------------------------------------------------------------------
export const MERGE_FIELDS = {
  "Property ID": true,
  "Property Name": true,
  "Property Type": true,
  "Address": true,
  "City": true,
  "State": true,
  "Zip Code": true,
  "Year Built": true,
  "Building Class": true,
  "Gross Building Area (Sq Ft)": true,
  "Net Rentable Area (Sq Ft)": true,
  "Land Area (Acres)": true,
  "Number of Floors": true,
  "Total Rental Units": true,
  "Property Manager": true,
  "Owner Name": true,
  "Appraisal Date": true,
  "Market Cap Rate": true,
  "Average Annual Operating Expense": true,
  "Average Annual Maintenance Expense": true,
  "Property Condition": true
};