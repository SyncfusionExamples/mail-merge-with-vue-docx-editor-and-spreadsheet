/**
 * Multi-app service path helper
 * 
 * Handles base path prefix for API calls in multi-app service deployments.
 * 
 * When deployed to GCP Load Balancer with path-based routing:
 *   Frontend URL: https://syncfusiondemo.com/vue-spreadsheet-docx-mail-merge/
 *   API calls need: /vue-spreadsheet-docx-mail-merge/api/... (with base path)
 *   
 * When in local development:
 *   Frontend URL: http://localhost:5175
 *   API calls need: /api/... (without base path, Vite proxy handles routing)
 */

/**
 * Get the base path from the VITE_APP_BASE_PATH environment variable
 * @returns {string} Base path without trailing slash (e.g., '/vue-spreadsheet-docx-mail-merge')
 * 
 * In local development: Returns empty string (VITE_APP_BASE_PATH not set)
 * In production: Returns the base path from Docker build-arg
 */
export function getBasePath() {
  const basePath = import.meta.env.VITE_APP_BASE_PATH || '/';
  return basePath.replace(/\/$/, ''); // Remove trailing slash
}

/**
 * Build an API path with base path prefix for multi-app service deployments
 * 
 * @param {string} endpoint - The API endpoint (e.g., '/api/DocumentEditor/Save')
 * @returns {string} Full API path
 * 
 * Examples:
 *   Dev (no base path):
 *     getApiPath('/OpenRentRoll') → '/OpenRentRoll'
 *     getApiPath('/api/DocumentEditor/Save') → '/api/DocumentEditor/Save'
 *   
 *   Prod (with base path):
 *     getApiPath('/OpenRentRoll') → '/vue-spreadsheet-docx-mail-merge/OpenRentRoll'
 *     getApiPath('/api/DocumentEditor/Save') → '/vue-spreadsheet-docx-mail-merge/api/DocumentEditor/Save'
 */
export function getApiPath(endpoint) {
  const basePath = getBasePath();
  
  // If no base path (development), return endpoint as-is
  // Vite dev server proxy will handle routing to http://127.0.0.1:5000
  if (!basePath) {
    return endpoint;
  }
  
  // If we have a base path (production), prepend it
  // This ensures GCP Load Balancer routes to correct app service
  return `${basePath}${endpoint}`;
}

/**
 * Build a static file URL with base path prefix
 * Useful for references to CSS, JS, or image files from HTML/CSS/JS
 * 
 * @param {string} filepath - The file path (e.g., '/assets/main.js')
 * @returns {string} Full file path
 */
export function getStaticPath(filepath) {
  const basePath = getBasePath();
  if (!basePath) return filepath;
  return `${basePath}${filepath}`;
}
