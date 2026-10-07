from flask import Flask, json, request, Response, send_file
from flask_cors import CORS #import CORS from flask_cors

import os
import sys

# Ensure CoreCLR is configured for pythonnet when running .NET 10
os.environ.setdefault("PYTHONNET_RUNTIME", "coreclr")
try:
    import pythonnet
    pythonnet.load("coreclr")
except Exception:
    pass

import clr #import clr from pythonnet
from io import BytesIO

app = Flask(
__name__,
static_folder='frontend/dist',
static_url_path=''
)

# ---- Minimal CORS + large-file support ----
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024 # 500 MB
app.config['MAX_FORM_MEMORY_SIZE'] = 500 * 1024 * 1024 # 500 MB


CORS(
    app,
    resources={r"/*": {"origins": "*"}},
    supports_credentials=False,
    expose_headers=["Content-Disposition", "Content-Length", "Content-Type"],
)

# Force CORS headers on EVERY response (including 413/500 errors)
@app.after_request
def add_cors_on_errors(resp):
    resp.headers["Access-Control-Allow-Origin"]  = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return resp
# -------------------------------------------

# get the current working directory
current_working_directory = os.getcwd()
# Load DLLs from the publish folder
publish_base = os.path.join(current_working_directory, "NETStandardWrapperLibrary", "WebServiceLibrary", "bin", "Release", "net10.0", "publish")
if os.path.exists(publish_base) and publish_base not in sys.path:
    sys.path.append(publish_base)

# Add references to published DLLs
if os.path.exists(publish_base):
    for dll_file in sorted(os.listdir(publish_base)):
        if dll_file.endswith(".dll"):
            try:
                clr.AddReference(os.path.join(publish_base, dll_file))
            except Exception:
                pass

#import our SpreadsheetEditor class from our C# namespace WebServiceLibrary
try:
    from WebServiceLibrary import SpreadsheetEditor
except ImportError:
    from SpreadsheetLibrary import SpreadsheetEditor
from Syncfusion.EJ2.Spreadsheet import SaveSettings, SaveType
from Syncfusion.Licensing import SyncfusionLicenseProvider
from System import Enum
from System.IO import SeekOrigin

# Register Syncfusion license
LICENSE_KEY = os.environ.get("SYNCFUSION_LICENSE_KEY", "")
SyncfusionLicenseProvider.RegisterLicense(LICENSE_KEY)

spreadEditor = SpreadsheetEditor() #create our SpreadsheetEditor object

@app.route('/Open', methods=['POST'])
def openExcel():
    if 'file' in request.files:
        files = request.files['file']
        # Get the stream data
        print(files)
        stream_data = files.stream.read()
        # Calling our Open method from our SpreadsheetEditor class which will return the Workbook JSON string
        return spreadEditor.Open(stream_data)
    else:
        return ""

@app.route('/Save', methods=['POST'])
def saveExcel():
    try:
        # Extract parameters from form data
        json_data = request.form.get('JSONData', '')
        save_type = request.form.get('saveType', 'Xlsx')  # Default to Xlsx
        file_name = request.form.get('fileName', 'Sample')
        
        # Extract PDF layout settings if provided
        pdf_layout_settings = request.form.get('pdfLayoutSettings', '{}')
        
        # Create SaveSettings object
        save_settings = SaveSettings()
        save_settings.JSONData = json_data
        # Convert string to SaveType enum
        save_settings.SaveType = Enum.Parse(SaveType, save_type)
        save_settings.FileName = file_name
        save_settings.PdfLayoutSettings = pdf_layout_settings
        
        # Call the Save method from SpreadsheetEditor class
        file_stream = spreadEditor.Save(save_settings)
        
        # Convert .NET MemoryStream to bytes
        file_stream.Seek(0, SeekOrigin.Begin)  # Seek to beginning
        stream_bytes = file_stream.ToArray()  # Convert to byte array
        file_stream.Dispose()  # Clean up the stream
        
        # Convert bytes to BytesIO for Flask
        output = BytesIO(stream_bytes)
        output.seek(0)
        
        extension = f".{save_type.lower()}"
        # Get the mime type based on the save type.
        mime_type = {
            "xls":  "application/vnd.ms-excel",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "pdf": "application/pdf",
            "csv": "text/csv"
        }.get(save_type.lower(), "application/octet-stream")

        return send_file(
            output,
            as_attachment=True,
            download_name=f"{file_name}{extension}",
            mimetype=mime_type
        )

    except Exception as e:
        import traceback
        error_msg = f"Error saving file: {str(e)}\n{traceback.format_exc()}"
        print(error_msg)
        return error_msg, 500



@app.route('/OpenRentRoll', methods=['GET'])
def open_rent_roll():
    """
    Server-side file open flow.

    """
    try:
        # Build the absolute path to the bundled rent roll file.
        # current_working_directory is set at startup to the folder
        # that contains app.py.
        files_dir = os.path.join(current_working_directory, "Files")
        file_path = os.path.join(files_dir, "rentRollDetails.xlsx")

        if not os.path.exists(file_path):
            error_payload = json.dumps(
                {"error": f"Rent roll file not found: {file_path}"}
            )
            return Response(
                error_payload, status=404, mimetype='application/json'
            )

        # Read the file as bytes and hand them to the C# Open process.
        with open(file_path, 'rb') as f:
            stream_data = f.read()

        # spreadEditor.Open returns the workbook as a JSON string
        # produced by Syncfusion.EJ2.Spreadsheet.SheetOpen.ProcessWorkBook.
        result = spreadEditor.Open(stream_data)

        # Send the JSON workbook back to the client.
        return Response(result, mimetype='application/json')

    except Exception as e:
        import traceback
        error_msg = (
            f"Error opening rent roll: {str(e)}\n{traceback.format_exc()}"
        )
        print(error_msg)
        error_payload = json.dumps({"error": error_msg})
        return Response(
            error_payload, status=500, mimetype='application/json'
        )


@app.route('/SaveRentRoll', methods=['POST'])
def save_rent_roll():
    """
    Save the rent roll by replacing the existing rentRollDetails.xlsx file.
    Instead of downloading the file, this saves it back to the Files folder.
    """
    try:
        # Extract parameters from form data
        json_data = request.form.get('JSONData', '')
        save_type = request.form.get('saveType', 'Xlsx')  # Default to Xlsx
        file_name = request.form.get('fileName', 'rentRollDetails')  # rentRollDetails
        
        # Extract PDF layout settings if provided
        pdf_layout_settings = request.form.get('pdfLayoutSettings', '{}')
        
        # Create SaveSettings object
        save_settings = SaveSettings()
        save_settings.JSONData = json_data
        # Convert string to SaveType enum
        save_settings.SaveType = Enum.Parse(SaveType, save_type)
        save_settings.FileName = file_name
        save_settings.PdfLayoutSettings = pdf_layout_settings
        
        # Call the Save method from SpreadsheetEditor class
        file_stream = spreadEditor.Save(save_settings)
        
        # Convert .NET MemoryStream to bytes
        file_stream.Seek(0, SeekOrigin.Begin)  # Seek to beginning
        stream_bytes = file_stream.ToArray()  # Convert to byte array
        
        # Convert .NET byte array to Python bytes
        # Use bytearray to handle the .NET array properly
        python_bytes = bytes(bytearray(stream_bytes))
        file_stream.Dispose()  # Clean up the stream
        
        # Build the path to the Files folder and save the file there
        files_dir = os.path.join(current_working_directory, "Files")
        
        # Ensure the Files directory exists
        if not os.path.exists(files_dir):
            os.makedirs(files_dir)
        
        # Construct the file path with the appropriate extension
        extension = f".{save_type.lower()}"
        file_path = os.path.join(files_dir, f"{file_name}{extension}")
        
        # Write the bytes to the file (replaces existing file if it exists)
        with open(file_path, 'wb') as f:
            f.write(python_bytes)
        
        # Return success response
        response_payload = json.dumps({
            "success": True,
            "message": f"File saved successfully to {file_path}",
            "filePath": file_path
        })
        return Response(response_payload, status=200, mimetype='application/json')

    except Exception as e:
        import traceback
        error_msg = f"Error saving rent roll: {str(e)}\n{traceback.format_exc()}"
        print(error_msg)
        error_payload = json.dumps({"error": error_msg})
        return Response(
            error_payload, status=500, mimetype='application/json'
        )


@app.route("/LicenseKey", methods=["GET"])
def license_key():
    # Lets the frontend register the key at runtime from the Azure app setting.
    return Response(LICENSE_KEY, mimetype="text/plain")


@app.route("/")
def home():
    return app.send_static_file("index.html")

if __name__ == "__main__":
    # threaded=True so large uploads don't block the dev server
    app.run(host="0.0.0.0", port=5000, threaded=True, debug=True) # http://localhost:5000/
    # app.run(host='', port=5001, debug=True) # http://localhost:5001/
