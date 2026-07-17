import json
import subprocess
import threading
import time

from subburn.paths import JOBS_DIR

# NOTE: this module must never import subburn.core.pipeline (it would create
# a cycle: pipeline -> engines -> whisper_asr/etc -> jobs -> pipeline). Engine,
# media, and subtitle modules should only ever import from here, never from
# core.pipeline.

JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()

# This machine has one GPU and limited RAM; running two heavy jobs (whisper +
# pyannote + ffmpeg encode) at once can exhaust memory and hang the whole
# system, not just the Python process. Serialize the actual processing so
# only one job's pipeline runs at a time; extra jobs just wait as "queued".
PROCESSING_LOCK = threading.Lock()


class JobCancelled(Exception):
    pass


# ffmpeg subprocesses currently running per job, so a cancel request can kill
# them immediately instead of waiting for the stage to finish on its own.
RUNNING_PROCS: dict[str, subprocess.Popen] = {}
RUNNING_PROCS_LOCK = threading.Lock()


def register_proc(job_id: str, proc: subprocess.Popen):
    with RUNNING_PROCS_LOCK:
        RUNNING_PROCS[job_id] = proc


def unregister_proc(job_id: str):
    with RUNNING_PROCS_LOCK:
        RUNNING_PROCS.pop(job_id, None)


def is_cancel_requested(job_id: str) -> bool:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        return bool(job and job.get("cancel_requested"))


def check_cancelled(job_id: str):
    if is_cancel_requested(job_id):
        raise JobCancelled()


def update_job(job_id: str, **kwargs):
    with JOBS_LOCK:
        JOBS[job_id].update(kwargs)
        job = JOBS[job_id]
        # Rough ETA from how long this job's actual processing has taken so
        # far vs. how much percent that bought - noisy early on and skewed
        # whenever a stage's pace differs from the rest (e.g. burn-in encodes
        # faster per-percent than transcription), but still a useful estimate.
        started = job.get("processing_started_at")
        pct = job.get("percent") or 0
        if started and 0 < pct < 100 and job.get("status") not in ("done", "error"):
            elapsed = time.time() - started
            job["eta_seconds"] = max(0, round(elapsed / pct * (100 - pct)))
        else:
            job["eta_seconds"] = None
        snapshot = dict(job)
    # Mirrored to disk so that if the process (or the whole machine) dies
    # mid-job, there's still a record of what was running and how far it got -
    # the in-memory JOBS dict alone doesn't survive a crash.
    try:
        (JOBS_DIR / job_id / "job.json").write_text(json.dumps(snapshot, default=str), encoding="utf-8")
    except OSError:
        pass
