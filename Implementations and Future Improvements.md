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
- A failed media request is reported and is not recorded as a successfully
  materialized Drive item.

### Collision-safe local paths

- Drive item names are not guaranteed to be unique within one Drive folder.
- Before processing every listed file, folder, or shortcut, the utility checks
  whether the equivalent local path is already occupied.
- On a conflict, it preserves the existing path and uses the listed item's full
  Drive ID in the name, for example `report__<drive-item-id>.pdf` or
  `Photos__<drive-item-id>`.
- If that generated name is also occupied, it appends an incrementing suffix.
- This prevents overwriting local content and ensures `shutil.move()` receives
  a new destination path instead of moving an item inside an existing folder.

### Drive shortcuts

- The listing response requests `shortcutDetails(targetId, targetMimeType)`.
- The utility records the local materialization path for each encountered Drive
  item ID.
- If a shortcut target was already materialized, the shortcut becomes a
  relative local symlink to that path.
- If a shortcut appears before its regular Drive item, the target is first
  materialized at the shortcut's location. When its regular location is later
  encountered, the item is moved there and the earlier shortcut location is
  replaced with a relative symlink.
- This applies to sibling shortcuts and shortcuts from a parent to one of its
  children, avoiding duplicate downloads while preserving both local paths.
- Move failures do not update the stored canonical path or discard the pending
  shortcut mapping.
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

### Local symlink support

Shortcut preservation relies on local filesystem symlinks. A future version
should provide a clearer fallback or explicit error handling for platforms and
directories where creating symlinks is not permitted.

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
