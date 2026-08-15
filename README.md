# Folder Fetcher

Folder Fetcher is a command-line utility for downloading a Google Drive folder
while preserving its original directory structure. Instead of relying on
Google's split ZIP downloads, it traverses the folder with the Google Drive API
and saves every file directly into its matching local directory.

It supports nested folders, paginated folder listings, file streaming, and
Google Drive shortcuts. A shortcut to an ancestor folder becomes a local
directory symlink so the download does not recurse forever.

## Usage

### Prerequisites

- Python 3
- A Google OAuth Desktop client configuration saved as `credentials.json` in
  this project directory

Install the required Google libraries in a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
```

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

## Further reading

- [Design analysis and possible approaches](Google%20Drive%20Large%20Folder%20Download%20Utility%20%E2%80%93%20Design%20Analysis.md)
- [Implemented behavior and future improvements](Implementations%20and%20Fututre%20Improvements.md)
