# Folder Fetcher

Folder Fetcher is a command-line utility for downloading a Google Drive folder
while preserving its original directory structure. Instead of relying on
Google's split ZIP downloads, it traverses the folder with the Google Drive API
and saves every file directly into its matching local directory.

It supports nested folders, paginated folder listings, streamed file downloads,
and Google Drive shortcuts. It preserves shortcut relationships with relative
local symlinks and avoids duplicate local names without overwriting files.

## Usage

### Prerequisites

- Python 3
- A Google Cloud project with the Google Drive API enabled
- A Google OAuth Desktop client configuration saved locally as
  `credentials.json`

Install the required Google libraries in a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
```

### Set up Google OAuth credentials

This repository does not include `credentials.json`. Each user must create
their own OAuth Desktop client before running the utility:

1. Open [Google Cloud Console](https://console.cloud.google.com/).
2. Create a Google Cloud project.
3. In **APIs & Services** → **Library**, enable **Google Drive API**.
4. In **Google Auth Platform**, configure the OAuth consent screen. Add your
   Google account as a test user if the app remains in testing mode.
5. Create an OAuth client of type **Desktop app**.
6. Download its JSON configuration and save it in this directory as
   `credentials.json`.

Do not commit `credentials.json` or `token.json` to Git. The first identifies
your OAuth application; the second authorizes access to your Google account.

Download a folder by URL:

```bash
python main.py "https://drive.google.com/drive/folders/YOUR_FOLDER_ID"
```

Or provide only the folder ID:

```bash
python main.py YOUR_FOLDER_ID
```

By default, downloads are placed in `downloads/<Drive folder name>/`. Choose a
different location with `--output` (or `-o`):

```bash
python main.py YOUR_FOLDER_ID --output "/path/to/downloads"
```

On first use, a browser window opens for Google sign-in and permission consent.
The resulting `token.json` is stored locally for later runs and must not be
shared or committed to Git.

### Naming conflicts

Google Drive allows different items in the same folder to use the same name.
If a local path is already occupied, Folder Fetcher preserves the existing item
and gives the next item a deterministic ID-based name:

```text
report.pdf  -> report__<drive-item-id>.pdf
Photos      -> Photos__<drive-item-id>
```

If that generated name is also occupied, an incrementing suffix is added.

## Further reading

- [Design analysis and possible approaches](Google%20Drive%20Large%20Folder%20Download%20Utility%20%E2%80%93%20Design%20Analysis.md)
- [Implemented behavior and future improvements](Implementations%20and%20Future%20Improvements.md)
