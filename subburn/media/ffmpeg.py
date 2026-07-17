import logging
import shutil
import subprocess
from pathlib import Path
from typing import Optional

import config as appconfig
from subburn.core.jobs import (
    JobCancelled,
    is_cancel_requested,
    register_proc,
    unregister_proc,
    update_job,
)

log = logging.getLogger("subburn")


def check_ffmpeg():
    if shutil.which("ffmpeg") is None:
        log.error("ffmpeg not found on PATH. Install it and restart the server.")
    else:
        log.info("ffmpeg found on PATH.")


def run_ffmpeg(args: list[str], job_id: Optional[str] = None):
    proc = subprocess.Popen(
        ["ffmpeg", "-y", *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if job_id:
        register_proc(job_id, proc)
    try:
        output, _ = proc.communicate()
    finally:
        if job_id:
            unregister_proc(job_id)
    if proc.returncode != 0:
        if job_id and is_cancel_requested(job_id):
            raise JobCancelled()
        raise RuntimeError(f"ffmpeg failed: {output[-3000:]}")


def extract_audio(job_id: str, video_path: Path, audio_path: Path):
    run_ffmpeg(
        ["-i", str(video_path), "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", str(audio_path)],
        job_id=job_id,
    )


def ffmpeg_escape_subtitles_path(path: Path) -> str:
    # ffmpeg's filtergraph parser treats ':' and '\' as special characters,
    # which collides with Windows drive letters (C:) and path separators.
    p = str(path).replace("\\", "/")
    p = p.replace(":", "\\:")
    return p


# NVENC (hardware H.264 encode on the GPU) is much faster than libx264 on a
# CPU-limited machine, but consumer NVIDIA drivers/GPUs occasionally reject it
# (session limits, an unsupported driver, etc.) - fall back to libx264 (CPU)
# in that case rather than failing the whole job, mirroring the CUDA->CPU
# fallback already used for whisper.
NVENC_VIDEO_ARGS = ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "20", "-b:v", "0"]
LIBX264_VIDEO_ARGS = ["-c:v", "libx264", "-preset", "fast", "-crf", "20"]


def _run_burn_encode(video_path: Path, vf: str, video_args: list[str], output_path: Path,
                      job_id: str, duration_ms: Optional[float]) -> tuple[int, list[str]]:
    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-i", str(video_path), "-vf", vf, *video_args,
         "-c:a", "aac", "-progress", "pipe:1", "-nostats", str(output_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    register_proc(job_id, proc)

    try:
        output_lines = []
        for line in proc.stdout:
            if is_cancel_requested(job_id):
                proc.terminate()
                break
            line = line.strip()
            output_lines.append(line)
            if line.startswith("out_time_ms=") and duration_ms:
                try:
                    out_ms = int(line.split("=", 1)[1])
                    percent = 75 + int(min(out_ms / duration_ms, 1.0) * 25)
                    update_job(job_id, percent=percent)
                except ValueError:
                    pass

        proc.wait()
    finally:
        unregister_proc(job_id)
    return proc.returncode, output_lines


def burn_subtitles(job_id: str, video_path: Path, srt_path: Path, output_path: Path):
    escaped = ffmpeg_escape_subtitles_path(srt_path)
    # Tahoma has solid coverage of Persian/Arabic, Latin, and Cyrillic scripts and
    # is bundled with Windows; the libass default font selection produced a
    # missing-glyph box for some Persian text.
    vf = f"subtitles='{escaped}':force_style='FontName=Tahoma'"

    duration_ms = None
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
             "default=noprint_wrappers=1:nokey=1", str(video_path)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        duration_ms = float(probe.stdout.strip()) * 1000
    except Exception:
        pass

    video_args = LIBX264_VIDEO_ARGS if appconfig.load().get("force_cpu") else NVENC_VIDEO_ARGS
    returncode, output_lines = _run_burn_encode(video_path, vf, video_args, output_path, job_id, duration_ms)

    if returncode != 0 and is_cancel_requested(job_id):
        raise JobCancelled()

    if returncode != 0 and video_args is NVENC_VIDEO_ARGS:
        log.warning("NVENC encode failed; falling back to CPU libx264 (%s)", chr(10).join(output_lines[-20:]))
        update_job(job_id, device_used_encode="cpu (libx264, fallback)")
        returncode, output_lines = _run_burn_encode(video_path, vf, LIBX264_VIDEO_ARGS, output_path, job_id, duration_ms)
    elif returncode == 0:
        update_job(job_id, device_used_encode="gpu (nvenc)" if video_args is NVENC_VIDEO_ARGS else "cpu (libx264)")

    if returncode != 0:
        raise RuntimeError(f"ffmpeg burn-in failed: {chr(10).join(output_lines[-100:])}")


def mux_softsub(job_id: str, video_path: Path, srt_path: Path, output_path: Path):
    # Softsub = embed the subtitles as a selectable track instead of baking
    # them into the video pixels. This is a stream copy (no re-encode), so
    # it's fast and lossless - but the player has to support picking a
    # subtitle track (not all iPhone video apps do; hardsub is the safe
    # choice there). Only the new subtitle track is mapped in: any subtitle
    # streams already present in the source are dropped so they can't be
    # mistaken for (or silently shadow) the one we just generated.
    duration_ms = None
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
             "default=noprint_wrappers=1:nokey=1", str(video_path)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        duration_ms = float(probe.stdout.strip()) * 1000
    except Exception:
        pass

    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-i", str(video_path), "-i", str(srt_path),
         "-map", "0:v", "-map", "0:a", "-map", "1:s",
         "-c:v", "copy", "-c:a", "copy", "-c:s", "srt",
         "-metadata:s:s:0", "title=Subtitles",
         "-progress", "pipe:1", "-nostats", str(output_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    register_proc(job_id, proc)

    try:
        output_lines = []
        for line in proc.stdout:
            if is_cancel_requested(job_id):
                proc.terminate()
                break
            line = line.strip()
            output_lines.append(line)
            if line.startswith("out_time_ms=") and duration_ms:
                try:
                    out_ms = int(line.split("=", 1)[1])
                    percent = 75 + int(min(out_ms / duration_ms, 1.0) * 25)
                    update_job(job_id, percent=percent)
                except ValueError:
                    pass

        proc.wait()
    finally:
        unregister_proc(job_id)

    if proc.returncode != 0 and is_cancel_requested(job_id):
        raise JobCancelled()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg softsub mux failed: {chr(10).join(output_lines[-100:])}")
