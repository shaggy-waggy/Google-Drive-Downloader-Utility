import argparse
import os.path
from pathlib import Path
from urllib.parse import urlparse

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

# If modifying these scopes, delete token.json and authenticate again.
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
SHORTCUTS_MIME_TYPE = "application/vnd.google-apps.shortcut"


def get_credentials():
    """Load, refresh, or create the OAuth credentials used by Drive."""
    creds = None

    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open("token.json", "w", encoding="utf-8") as token:
            token.write(creds.to_json())

    return creds


def get_folder_id(folder_id_or_url):
    """Return a folder ID from either a Drive folder ID or a Drive folder URL."""
    if "://" not in folder_id_or_url:
        return folder_id_or_url

    path_parts = [part for part in urlparse(folder_id_or_url).path.split("/") if part]
    try:
        return path_parts[path_parts.index("folders") + 1]
    except (ValueError, IndexError) as error:
        raise ValueError(
            "Provide a Google Drive folder URL containing '/folders/<folder-id>' "
            "or a folder ID."
        ) from error


def parse_arguments():
    """Parse command-line options for the downloader."""
    parser = argparse.ArgumentParser(
        description="Download a Google Drive folder while preserving its structure."
    )
    parser.add_argument(
        "folder",
        help="Google Drive folder ID or URL, for example https://drive.google.com/drive/folders/<id>",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="downloads",
        help="Local directory where the folder contents will be downloaded (default: downloads).",
    )
    return parser.parse_args()


class DriveDownloader:
    """Traverse Google Drive folders and download their contents locally."""

    def __init__(self, credentials, output_dir):
        self.service = build("drive", "v3", credentials=credentials)
        self.output_dir = Path(output_dir)

    def get_folder_name(self, folder_id):
        """Return the name of a Drive folder, validating the supplied ID."""
        folder = self.service.files().get(
            fileId=folder_id,
            fields="name, mimeType",
        ).execute()

        if folder.get("mimeType") != FOLDER_MIME_TYPE:
            raise ValueError("The supplied ID or URL does not refer to a Drive folder.")

        return folder["name"]

    def list_folder_contents(self, folder_id):
        """Return every non-trashed item directly inside a Drive folder."""
        items = []
        page_token = None

        while True:
            response = self.service.files().list(
                q=f"'{folder_id}' in parents and trashed = false",
                fields=(
                    "nextPageToken, files(id, name, mimeType, size, md5Checksum, "
                    "shortcutDetails(targetId, targetMimeType))"
                ),
                pageSize=1000,
                pageToken=page_token,
            ).execute()
            items.extend(response.get("files", []))

            page_token = response.get("nextPageToken")
            if page_token is None:
                return items

    def download_file(self, file_id, destination_path):
        """Stream one non-Google-native Drive file directly to disk."""
        destination_path = Path(destination_path)
        destination_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            request = self.service.files().get_media(fileId=file_id)

            with destination_path.open("wb") as local_file:
                downloader = MediaIoBaseDownload(local_file, request)
                done = False

                while not done:
                    status, done = downloader.next_chunk()
                    if status:
                        print(f"{destination_path.name}: {status.progress() * 100:.0f}%")
        except HttpError as error:
            print(f"Could not download {destination_path}: {error}")
            return False

        print(f"Downloaded: {destination_path}")
        return True

    def create_folder_shortcut(self, shortcut_path, target_path):
        """Create a relative local directory symlink for an ancestor shortcut."""
        shortcut_path = Path(shortcut_path)
        target_path = Path(target_path)
        shortcut_path.parent.mkdir(parents=True, exist_ok=True)

        if shortcut_path.exists() or shortcut_path.is_symlink():
            print(f"Skipped existing shortcut path: {shortcut_path}")
            return

        relative_target = os.path.relpath(target_path, shortcut_path.parent)
        shortcut_path.symlink_to(relative_target, target_is_directory=True)
        print(f"Created folder shortcut: {shortcut_path} -> {relative_target}")

    def download_folder_recursive(self, folder_id, local_path=None, ancestor_folders=None):
        """Recreate a Drive folder tree at local_path and download its files."""
        if local_path is None:
            local_path = self.output_dir / self.get_folder_name(folder_id)
        else:
            local_path = Path(local_path)
        ancestor_folders = {} if ancestor_folders is None else ancestor_folders

        if folder_id in ancestor_folders:
            self.create_folder_shortcut(local_path, ancestor_folders[folder_id])
            return

        ancestor_folders = {**ancestor_folders, folder_id: local_path}
        local_path.mkdir(parents=True, exist_ok=True)

        for item in self.list_folder_contents(folder_id):
            destination_path = local_path / item["name"]

            if item["mimeType"] == FOLDER_MIME_TYPE:
                self.download_folder_recursive(
                    item["id"], destination_path, ancestor_folders
                )
            elif item["mimeType"] == SHORTCUTS_MIME_TYPE:
                shortcut_details = item.get("shortcutDetails", {})
                target_id = shortcut_details.get("targetId")
                target_mime_type = shortcut_details.get("targetMimeType")

                if not target_id or not target_mime_type:
                    print(f"Skipped unresolved shortcut: {item['name']}")
                elif target_mime_type == SHORTCUTS_MIME_TYPE:
                    print(f"Skipped shortcut targeting another shortcut: {item['name']}")
                elif target_mime_type == FOLDER_MIME_TYPE:
                    self.download_folder_recursive(
                        target_id, destination_path, ancestor_folders
                    )
                else:
                    self.download_file(target_id, destination_path)
            else:
                self.download_file(item["id"], destination_path)


def main():
    try:
        args = parse_arguments()
        folder_id = get_folder_id(args.folder)
        downloader = DriveDownloader(get_credentials(), output_dir=args.output)
        print("Google Drive API service created successfully.")
        downloader.download_folder_recursive(folder_id)
    except (HttpError, ValueError) as error:
        print(f"An error occurred: {error}")


if __name__ == "__main__":
    main()
