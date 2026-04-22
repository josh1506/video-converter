from __future__ import annotations

import os
import shutil
import subprocess
import uuid
from pathlib import Path


class ConversionError(Exception):
    """Raised when ffmpeg conversion fails."""


def resolve_ffmpeg_binary() -> str:
    env_binary = os.getenv("FFMPEG_BINARY", "").strip()
    if env_binary and Path(env_binary).exists():
        return env_binary

    in_path = shutil.which("ffmpeg")
    if in_path:
        return in_path

    local_app_data = os.getenv("LOCALAPPDATA", "")
    if local_app_data:
        winget_packages = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
        if winget_packages.exists():
            matches = winget_packages.glob("Gyan.FFmpeg*/*/bin/ffmpeg.exe")
            fallback = next(matches, None)
            if fallback and fallback.exists():
                return str(fallback)

    raise ConversionError(
        "ffmpeg is not installed or is not available on PATH. Install ffmpeg and try again."
    )


def ensure_ffmpeg_available() -> str:
    return resolve_ffmpeg_binary()


def convert_video(
    input_path: Path,
    output_dir: Path,
    output_format: str,
    output_stem: str | None = None,
) -> Path:
    ffmpeg_binary = ensure_ffmpeg_available()
    output_dir.mkdir(parents=True, exist_ok=True)

    safe_stem = (
        (output_stem or input_path.stem).strip().replace("/", "_").replace("\\", "_")
    )
    if not safe_stem:
        safe_stem = "video"

    output_file = output_dir / f"{safe_stem}-{uuid.uuid4().hex[:8]}.{output_format}"

    command = [
        ffmpeg_binary,
        "-y",
        "-i",
        str(input_path),
        str(output_file),
    ]

    process = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=1200,
        check=False,
    )

    if process.returncode != 0:
        stderr = process.stderr.strip()
        error_excerpt = (
            "\n".join(stderr.splitlines()[-6:]) if stderr else "Unknown ffmpeg error."
        )
        raise ConversionError(f"Conversion failed. ffmpeg said:\n{error_excerpt}")

    if not output_file.exists() or output_file.stat().st_size == 0:
        raise ConversionError("Conversion did not produce a valid output file.")

    return output_file
