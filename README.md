# Video Converter

A Django-based drag-and-drop video converter that uses ffmpeg on the server.

## Features

- Drag-and-drop file upload (single or multiple files).
- Converts uploaded video(s) to the output format selected by the user.
- Supports common output formats from a dropdown and custom format input.
- Live progress tracking with remaining count and ETA.
- Converted file list with one-by-one download links.
- Bulk download dropdown to download all converted outputs as ZIP.

## Important Note About "Any" Format

This project accepts any input file extension and allows users to request any output container/format string.
Actual support depends on your installed ffmpeg build and codecs.

## Requirements

- Python 3.13+
- ffmpeg installed and available in your system PATH

### Install ffmpeg on Windows

Use winget:

```powershell
winget install --id Gyan.FFmpeg --source winget
```

Then restart your terminal and verify:

```powershell
ffmpeg -version
```

## Run Locally

1. Install dependencies:

```powershell
uv sync
```

2. Apply migrations:

```powershell
uv run python manage.py migrate
```

3. Start the server:

```powershell
uv run python manage.py runserver
```

4. Open the app:

http://127.0.0.1:8000/

## How Conversion Works

- Uploaded files are temporarily written to `media/inputs/`.
- A background conversion job runs with ffmpeg and writes outputs to `media/outputs/`.
- The frontend polls job status to show progress, remaining files, and ETA.
- Completed videos appear in a download list for one-at-a-time download.
- Users can also choose bulk ZIP download from the dropdown.
