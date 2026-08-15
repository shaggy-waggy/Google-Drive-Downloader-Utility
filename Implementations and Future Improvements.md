# Implemented behavior and future improvements

## Command-line use

Run the utility with a Google Drive folder ID or a Google Drive folder URL:

```bash
./.venv/bin/python main.py "https://drive.google.com/drive/folders/YOUR_FOLDER_ID"
```

Choose a different local destination with `--output` (or `-o`):

```bash
./.venv/bin/python main.py YOUR_FOLDER_ID --output "/path/to/downloads"
```

## Fixed or implemented

### Shared Drive API client

- Replaced the module-level global `service` variable with `DriveDownloader`.
- Authentication is performed once by `get_credentials()`.
- `DriveDownloader` creates one authenticated `self.service`, which every
  listing and download method reuses.
- This fixes the original scope problem where `creds` was local to the setup
  function but used from `main()`.

### Folder traversal and pagination

- `list_folder_contents(folder_id)` uses the Drive query
  `'<folder_id>' in parents and trashed = false` to retrieve a folder's direct
  children from Google Drive.
- It asks for up to 1,000 children per request.
- When Drive returns `nextPageToken`, the same query is issued again with that
  token. The token is Google's cursor for the next result page.
- `download_folder_recursive()` creates the corresponding local directory,
  recurses into folders, and downloads normal files to their matching local
  paths.
- The initial download creates `downloads/<root Drive folder name>/`, so the
  selected Drive folder remains the outermost local directory.

### Streaming file downloads

- Files are streamed directly to the destination file with
  `MediaIoBaseDownload`.
- The utility no longer stores an entire downloaded file in memory before
  writing it, which is important for large files.

### Drive shortcuts

- The listing response requests `shortcutDetails(targetId, targetMimeType)`.
- A shortcut to a normal file downloads the target file at the shortcut's
  current local path.
- A shortcut to a folder recursively downloads the target folder beneath a
  local directory named after the shortcut.
- A shortcut to an ancestor folder creates a relative local directory symlink
  instead of repeatedly traversing the same tree. This preserves the alias and
  prevents infinite recursion.
- Missing shortcut metadata is reported and skipped safely.
- Google Drive does not allow a shortcut to target another shortcut, but the
  code explicitly detects that unexpected MIME type and avoids trying to
  download shortcut metadata with `get_media()`.

## Future improvements

### Parallel downloads

The downloader is intentionally serial for now: traversal lists folders and
downloads one file at a time. A future version can use a bounded thread pool
to download several files concurrently while one coordinator continues folder
traversal.

- Use a conservative, configurable worker count (for example, 3–8).
- Give each worker its own Drive API service instance; do not share one client
  across threads.
- Add retry logic with exponential backoff for temporary network, quota, and
  rate-limit failures.

### Repeated non-ancestor folder shortcuts

Only folders in the current ancestry path are mapped today. Therefore, if a
shortcut points to a sibling or another already-downloaded folder, its contents
are downloaded again at the shortcut's location. This preserves the shortcut's
position but can duplicate data.

The same applies when a parent folder contains both a real child folder and a
shortcut pointing to that child. The child is not an ancestor of its parent, so
the shortcut is expanded into a second local copy rather than becoming a local
alias. The order in which Drive returns the child and shortcut does not change
this behavior.

A future optimization can maintain a global mapping from Drive folder ID to
its first local path. When a later shortcut targets an already-downloaded
folder, create a local symlink to that path instead of downloading the content
again. This needs a clear policy for targets that have not yet been downloaded.

### File-shortcut names

A shortcut to a file currently uses the shortcut's name as its local filename.
That name may not include the target file extension. A future version can fetch
the target's name or file extension and choose a local filename that preserves
the extension.

### Google-native files

Google Docs, Sheets, and Slides cannot be downloaded through `get_media()`.
The downloader should later detect Google Workspace MIME types and use
`files.export()` with selected output formats such as DOCX, XLSX, or PDF.

### Resume and verification

- Skip files that already exist with the expected size or checksum.
- Store progress in a manifest so interrupted downloads can resume.
- Verify downloaded binary files against the Drive `md5Checksum` when present.
