from __future__ import annotations

import io
import mimetypes
import os
import threading
import time
import uuid
import zipfile
from pathlib import Path

from django.conf import settings
from django.http import Http404
from django.http import FileResponse, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.text import get_valid_filename
from django.views.decorators.http import require_POST

from .forms import ConversionRequestForm, SUPPORTED_OUTPUT_FORMATS
from .services import ConversionError, convert_video


JOB_LOCK = threading.Lock()
CONVERSION_JOBS: dict[str, dict] = {}


def _get_job(job_id: str) -> dict:
    with JOB_LOCK:
        job = CONVERSION_JOBS.get(job_id)
        if not job:
            raise Http404("Conversion job not found.")
        return job


def _create_job(uploaded_files: list, output_format: str) -> str:
    job_id = uuid.uuid4().hex
    input_dir = Path(settings.MEDIA_ROOT) / "inputs"
    output_dir = Path(settings.MEDIA_ROOT) / "outputs"
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    items = []
    for index, uploaded_file in enumerate(uploaded_files):
        original_name = uploaded_file.name
        original_suffix = Path(original_name).suffix
        input_name = f"{job_id}-{index + 1}-{uuid.uuid4().hex}{original_suffix}"
        input_path = input_dir / input_name

        with input_path.open("wb+") as destination:
            for chunk in uploaded_file.chunks():
                destination.write(chunk)

        items.append(
            {
                "index": index,
                "original_name": original_name,
                "input_path": str(input_path),
                "output_path": None,
                "output_name": None,
                "status": "queued",
                "error": None,
                "duration_seconds": None,
            }
        )

    with JOB_LOCK:
        CONVERSION_JOBS[job_id] = {
            "id": job_id,
            "output_format": output_format,
            "status": "running",
            "started_at": time.time(),
            "finished_at": None,
            "items": items,
        }

    return job_id


def _run_conversion_job(job_id: str) -> None:
    with JOB_LOCK:
        job = CONVERSION_JOBS.get(job_id)
        if not job:
            return
        items = list(job["items"])
        output_format = job["output_format"]

    output_dir = Path(settings.MEDIA_ROOT) / "outputs"

    for item in items:
        input_path = Path(item["input_path"])
        start_time = time.time()

        with JOB_LOCK:
            job = CONVERSION_JOBS.get(job_id)
            if not job:
                return
            job["items"][item["index"]]["status"] = "processing"

        base_stem = get_valid_filename(Path(item["original_name"]).stem) or "video"
        output_stem = f"{base_stem}-{job_id[:8]}-{item['index'] + 1}"

        try:
            output_path = convert_video(
                input_path=input_path,
                output_dir=output_dir,
                output_format=output_format,
                output_stem=output_stem,
            )
            duration = max(0.0, time.time() - start_time)
            with JOB_LOCK:
                job = CONVERSION_JOBS.get(job_id)
                if not job:
                    return
                job_item = job["items"][item["index"]]
                job_item["status"] = "completed"
                job_item["output_path"] = str(output_path)
                job_item["output_name"] = output_path.name
                job_item["duration_seconds"] = duration
        except ConversionError as exc:
            duration = max(0.0, time.time() - start_time)
            with JOB_LOCK:
                job = CONVERSION_JOBS.get(job_id)
                if not job:
                    return
                job_item = job["items"][item["index"]]
                job_item["status"] = "failed"
                job_item["error"] = str(exc)
                job_item["duration_seconds"] = duration
        except Exception as exc:  # noqa: BLE001
            duration = max(0.0, time.time() - start_time)
            with JOB_LOCK:
                job = CONVERSION_JOBS.get(job_id)
                if not job:
                    return
                job_item = job["items"][item["index"]]
                job_item["status"] = "failed"
                job_item["error"] = f"Unexpected error: {exc}"
                job_item["duration_seconds"] = duration
        finally:
            input_path.unlink(missing_ok=True)

    with JOB_LOCK:
        job = CONVERSION_JOBS.get(job_id)
        if not job:
            return
        has_failure = any(item["status"] == "failed" for item in job["items"])
        has_success = any(item["status"] == "completed" for item in job["items"])
        if has_success and not has_failure:
            job["status"] = "completed"
        elif has_success and has_failure:
            job["status"] = "completed_with_errors"
        else:
            job["status"] = "failed"
        job["finished_at"] = time.time()


def index(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "converter/index.html",
        {"output_formats": SUPPORTED_OUTPUT_FORMATS},
    )


@require_POST
def convert_file(request: HttpRequest) -> JsonResponse:
    form = ConversionRequestForm(request.POST, request.FILES)

    if not form.is_valid():
        errors = []
        for key, field_errors in form.errors.items():
            label = "output_format"
            errors.extend([f"{label}: {error}" for error in field_errors])
        return JsonResponse({"error": " ".join(errors)}, status=400)

    uploaded_files = request.FILES.getlist("video_file")
    if not uploaded_files:
        return JsonResponse(
            {"error": "video_file: Please upload at least one file."}, status=400
        )

    output_format = form.cleaned_data["output_format"]
    job_id = _create_job(uploaded_files=uploaded_files, output_format=output_format)
    thread = threading.Thread(target=_run_conversion_job, args=(job_id,), daemon=True)
    thread.start()

    return JsonResponse(
        {
            "job_id": job_id,
            "status": "running",
            "total": len(uploaded_files),
            "status_url": reverse("converter:status", args=[job_id]),
            "zip_url": reverse("converter:download_zip", args=[job_id]),
        }
    )


def conversion_status(request: HttpRequest, job_id: str) -> JsonResponse:
    with JOB_LOCK:
        job = CONVERSION_JOBS.get(job_id)
        if not job:
            return JsonResponse({"error": "Job not found."}, status=404)

        items = list(job["items"])
        job_status = job["status"]
        started_at = job["started_at"]
        finished_at = job["finished_at"]

    total = len(items)
    completed = [item for item in items if item["status"] == "completed"]
    failed = [item for item in items if item["status"] == "failed"]
    processing_count = len([item for item in items if item["status"] == "processing"])
    done_count = len(completed) + len(failed)
    remaining_count = max(0, total - done_count)

    durations = [
        item["duration_seconds"]
        for item in items
        if item["duration_seconds"] is not None
    ]
    eta_seconds = None
    if remaining_count == 0:
        eta_seconds = 0
    elif durations:
        average_seconds = sum(durations) / len(durations)
        eta_seconds = int(max(0, round(average_seconds * remaining_count)))

    progress_percent = int((done_count / total) * 100) if total else 0
    elapsed_seconds = (
        int(max(0, (finished_at or time.time()) - started_at)) if started_at else 0
    )

    file_items = []
    for item in items:
        download_url = None
        if item["status"] == "completed" and item["output_name"]:
            download_url = reverse(
                "converter:download_single",
                args=[job_id, item["output_name"]],
            )
        file_items.append(
            {
                "original_name": item["original_name"],
                "output_name": item["output_name"],
                "status": item["status"],
                "error": item["error"],
                "download_url": download_url,
            }
        )

    return JsonResponse(
        {
            "job_id": job_id,
            "status": job_status,
            "total": total,
            "completed": len(completed),
            "failed": len(failed),
            "processing": processing_count,
            "remaining": remaining_count,
            "progress_percent": progress_percent,
            "eta_seconds": eta_seconds,
            "elapsed_seconds": elapsed_seconds,
            "output_format": job["output_format"],
            "zip_url": reverse("converter:download_zip", args=[job_id]),
            "files": file_items,
        }
    )


def download_single(request: HttpRequest, job_id: str, file_name: str) -> FileResponse:
    job = _get_job(job_id)
    matched_item = None
    for item in job["items"]:
        if item["output_name"] == file_name and item["status"] == "completed":
            matched_item = item
            break

    if not matched_item or not matched_item["output_path"]:
        raise Http404("File not available for download.")

    output_path = Path(matched_item["output_path"])
    if not output_path.exists():
        raise Http404("File not found.")

    guessed_type, _ = mimetypes.guess_type(str(output_path))
    content_type = guessed_type or "application/octet-stream"
    return FileResponse(
        output_path.open("rb"),
        as_attachment=True,
        filename=output_path.name,
        content_type=content_type,
    )


def download_zip(request: HttpRequest, job_id: str) -> FileResponse:
    job = _get_job(job_id)
    completed_items = [
        item
        for item in job["items"]
        if item["status"] == "completed" and item["output_path"]
    ]

    if not completed_items:
        raise Http404("No converted files available to zip.")

    archive_name = f"converted-videos-{job_id[:8]}.zip"
    archive_buffer = io.BytesIO()

    with zipfile.ZipFile(
        archive_buffer, "w", compression=zipfile.ZIP_DEFLATED
    ) as archive:
        for item in completed_items:
            path = Path(item["output_path"])
            if path.exists():
                archive.write(path, arcname=path.name)

    archive_buffer.seek(0)
    return FileResponse(
        archive_buffer,
        as_attachment=True,
        filename=archive_name,
        content_type="application/zip",
    )
