import os
import io
import pickle
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# --- CONFIGURATION ---
SCOPES = ['https://www.googleapis.com/auth/drive'] # Requires full access to allow deletion
DELETE_AFTER_DOWNLOAD = True  # Set to False if you want to keep the files in Drive
IDS_FILE = 'drive_ids.txt'
OUTPUT_DIR = './google_drive_downloaded'

# Mime types for Google Workspace files that need to be exported instead of raw download
GOOGLE_DOC_EXPORT_MAP = {
    'application/vnd.google-apps.document': ('application/pdf', '.pdf'),
    'application/vnd.google-apps.spreadsheet': ('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', '.xlsx'),
    'application/vnd.google-apps.presentation': ('application/vnd.openxmlformats-officedocument.presentationml.presentation', '.pptx')
}

def authenticate_drive():
    """Authenticates the user and returns the Google Drive API service."""
    creds = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
            
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
            
    return build('drive', 'v3', credentials=creds)

def download_file(service, file_id, file_name, mime_type, destination_dir):
    """Downloads a binary file or exports a Google Workspace file."""
    os.makedirs(destination_dir, exist_ok=True)
    file_name = file_name.replace('/', '_') # Prevent path traversal issues
    destination_path = os.path.join(destination_dir, file_name)

    try:
        if mime_type in GOOGLE_DOC_EXPORT_MAP:
            export_mime, ext = GOOGLE_DOC_EXPORT_MAP[mime_type]
            destination_path += ext
            request = service.files().export_media(fileId=file_id, mimeType=export_mime)
        else:
            request = service.files().get_media(fileId=file_id)

        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            
        with open(destination_path, 'wb') as f:
            f.write(fh.getvalue())
            
        print(f"Successfully downloaded: {destination_path}")
        return True
    except Exception as e:
        print(f"Error downloading file ID {file_id}: {e}")
        return False

def process_folder(service, folder_id, current_output_dir):
    """Recursively processes a folder ID from Drive."""
    os.makedirs(current_output_dir, exist_ok=True)
    page_token = None
    success = True

    while True:
        query = f"'{folder_id}' in parents and trashed = false"
        results = service.files().list(
            q=query,
            pageSize=100,
            fields="nextPageToken, files(id, name, mimeType)",
            pageToken=page_token
        ).execute()
        
        items = results.get('files', [])
        for item in items:
            item_id = item['id']
            item_name = item['name']
            mime_type = item['mimeType']
            
            if mime_type == 'application/vnd.google-apps.folder':
                sub_dir = os.path.join(current_output_dir, item_name)
                if process_folder(service, item_id, sub_dir):
                    # If folder and its contents processed successfully, delete the folder from Drive if enabled
                    if DELETE_AFTER_DOWNLOAD:
                        service.files().delete(fileId=item_id).execute()
                        print(f"Deleted folder from Google Drive: {item_name} ({item_id})")
            else:
                if download_file(service, item_id, item_name, mime_type, current_output_dir):
                    if DELETE_AFTER_DOWNLOAD:
                        service.files().delete(fileId=item_id).execute()
                        print(f"Deleted file from Google Drive: {item_name} ({item_id})")
                else:
                    success = False
                    
        page_token = results.get('nextPageToken')
        if not page_token:
            break
            
    return success

def main():
    if not os.path.exists(IDS_FILE):
        print(f"Error: '{IDS_FILE}' not found. Please create it and add Drive IDs.")
        return

    # Read IDs from file (ignoring empty lines and comments starting with #)
    with open(IDS_FILE, 'r') as f:
        file_ids = [line.strip() for line in f if line.strip() and not line.startswith('#')]

    if not file_ids:
        print(f"No IDs found in '{IDS_FILE}'.")
        return

    service = authenticate_drive()

    for file_id in file_ids:
        try:
            # Fetch metadata to check if it's a file or folder
            meta = service.files().get(fileId=file_id, fields="name, mimeType").execute()
            name = meta['name']
            mime_type = meta['mimeType']

            print(f"\nProcessing ID: {file_id} ({name})")

            if mime_type == 'application/vnd.google-apps.folder':
                folder_output_dir = os.path.join(OUTPUT_DIR, name)
                success = process_folder(service, file_id, folder_output_dir)
                
                # Delete the root folder itself if conditional check passes
                if success and DELETE_AFTER_DOWNLOAD:
                    service.files().delete(fileId=file_id).execute()
                    print(f"Deleted root folder from Google Drive: {name} ({file_id})")
            else:
                success = download_file(service, file_id, name, mime_type, OUTPUT_DIR)
                
                # --- IF-ELSE CONTROLLED DELETION ---
                if success:
                    if DELETE_AFTER_DOWNLOAD:
                        service.files().delete(fileId=file_id).execute()
                        print(f"Deleted file from Google Drive: {name} ({file_id})")
                    else:
                        print(f"Skipped deletion for {name} (DELETE_AFTER_DOWNLOAD is set to False).")
                else:
                    print(f"Skipped deletion for {name} due to download failure.")

        except Exception as e:
            print(f"Could not process ID {file_id}: {e}")

    print("\nAll tasks completed!")

if __name__ == '__main__':
    main()