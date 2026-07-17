import shutil
import threading
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from subburn.core.jobs import JOBS, JOBS_LOCK, RUNNING_PROCS, RUNNING_PROCS_LOCK, update_job
from subburn.core.pipeline import VALID_SUBTITLE_MODES, process_job
from subburn.engines.registry import get_asr_engine
from subburn.paths import JOBS_DIR
from subburn.subtitles.transcript import apply_speaker_names
from subburn.web.auth import require_auth

router = APIRouter(prefix="/api/jobs", dependencies=[Depends(require_auth)])


@router.post("")
async def create_job(
    video: UploadFile = File(...),
    target_lang: str = Form(""),
    source_lang: str = Form(""),
    model_size: str = Form("small"),
    diarize: bool = Form(False),
    subtitle_mode: str = Form("hardsub"),
):
    valid_model_sizes = set(get_asr_engine().list_available_models())
    if model_size not in valid_model_sizes:
        raise HTTPException(400, f"Invalid model_size. Must be one of {sorted(valid_model_sizes)}")
    if subtitle_mode not in VALID_SUBTITLE_MODES:
        raise HTTPException(400, f"Invalid subtitle_mode. Must be one of {sorted(VALID_SUBTITLE_MODES)}")

    job_id = uuid.uuid4().hex
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(video.filename or "input.mp4").suffix or ".mp4"
    video_path = job_dir / f"input{ext}"
    with open(video_path, "wb") as f:
        shutil.copyfileobj(video.file, f)

    with JOBS_LOCK:
        JOBS[job_id] = {
            "status": "queued",
            "percent": 0,
            "error": None,
            "created_at": time.time(),
            "processing_started_at": None,
            "eta_seconds": None,
            "filename": video.filename,
            "filesize": video_path.stat().st_size,
            "model_size": model_size,
            "target_lang": target_lang or None,
            "source_lang": source_lang or None,
            "diarize": diarize,
            "subtitle_mode": subtitle_mode,
            "detected_language": None,
            "device_used": None,
            "device_used_encode": None,
            "speakers": [],
            "speaker_names": {},
            "cancel_requested": False,
        }
    update_job(job_id)  # write the initial job.json snapshot to disk

    thread = threading.Thread(
        target=process_job,
        args=(job_id, video_path, model_size, target_lang or None, diarize, source_lang or None, subtitle_mode),
        daemon=True,
    )
    thread.start()

    return {"job_id": job_id}


@router.get("/{job_id}")
async def get_job(job_id: str):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is None:
            raise HTTPException(404, "Job not found")
        return dict(job)


@router.post("/{job_id}/cancel")
async def cancel_job(job_id: str):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is None:
            raise HTTPException(404, "Job not found")
        if job["status"] in ("done", "error", "cancelled", "cancelling"):
            raise HTTPException(409, f"Job already {job['status']}")
        job["cancel_requested"] = True

    with RUNNING_PROCS_LOCK:
        proc = RUNNING_PROCS.get(job_id)
    if proc and proc.poll() is None:
        # Kills whatever ffmpeg stage is currently running immediately; a
        # Python-level stage (transcribe/translate) instead notices the
        # cancel_requested flag at its next per-segment checkpoint. Diarization
        # is a single non-interruptible pyannote call, so a cancel during that
        # stage takes effect only once it finishes.
        try:
            proc.terminate()
        except Exception:
            pass

    update_job(job_id, status="cancelling")
    return {"ok": True}


@router.get("/{job_id}/download")
async def download_job(job_id: str):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is None:
            raise HTTPException(404, "Job not found")
        if job["status"] != "done":
            raise HTTPException(409, "Job is not finished yet")

    is_softsub = job.get("subtitle_mode") == "softsub"
    ext = ".mkv" if is_softsub else ".mp4"
    output_path = JOBS_DIR / job_id / f"output{ext}"
    if not output_path.exists():
        raise HTTPException(404, "Output file not found")

    media_type = "video/x-matroska" if is_softsub else "video/mp4"
    return FileResponse(output_path, media_type=media_type, filename=f"{job_id}{ext}")


@router.get("/{job_id}/transcript")
async def get_transcript(job_id: str):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is None:
            raise HTTPException(404, "Job not found")
        if job["status"] != "done":
            raise HTTPException(409, "Job is not finished yet")

    transcript_path = JOBS_DIR / job_id / "transcript.txt"
    if not transcript_path.exists():
        raise HTTPException(404, "Transcript not found")

    return FileResponse(transcript_path, media_type="text/plain; charset=utf-8", filename=f"{job_id}_transcript.txt")


class SpeakerRenameRequest(BaseModel):
    names: dict[str, str]


@router.post("/{job_id}/speakers")
async def rename_speakers(job_id: str, body: SpeakerRenameRequest):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is None:
            raise HTTPException(404, "Job not found")
        if job["status"] != "done":
            raise HTTPException(409, "Job is not finished yet")
        speakers = list(job.get("speakers") or [])
        if not speakers:
            raise HTTPException(400, "This job has no detected speakers to rename")
        speaker_names = dict(job.get("speaker_names", {}))

    for generic, custom in body.names.items():
        if generic in speakers and custom.strip():
            speaker_names[generic] = custom.strip()

    raw_path = JOBS_DIR / job_id / "transcript_raw.txt"
    if not raw_path.exists():
        raise HTTPException(404, "Transcript not found")

    raw_text = raw_path.read_text(encoding="utf-8")
    new_text = apply_speaker_names(raw_text, speakers, speaker_names)
    (JOBS_DIR / job_id / "transcript.txt").write_text(new_text, encoding="utf-8")

    update_job(job_id, speaker_names=speaker_names)
    return {"transcript": new_text, "speaker_names": speaker_names}
