import logging
import time
from pathlib import Path
from typing import Optional

from subburn.core.jobs import (
    JobCancelled,
    PROCESSING_LOCK,
    check_cancelled,
    unregister_proc,
    update_job,
)
from subburn.engines.registry import get_asr_engine, get_diarization_engine, get_translation_engine
from subburn.media.ffmpeg import burn_subtitles, extract_audio, mux_softsub
from subburn.subtitles.srt import write_srt
from subburn.subtitles.transcript import build_transcript

log = logging.getLogger("subburn")

VALID_SUBTITLE_MODES = {"hardsub", "softsub"}


def assign_speakers(segments: list[dict], turns: list[dict]) -> list[dict]:
    if not turns:
        return segments

    raw_to_friendly: dict[str, str] = {}
    next_index = 1
    labeled = []
    for seg in segments:
        best_turn = None
        best_overlap = 0.0
        for t in turns:
            overlap = min(seg["end"], t["end"]) - max(seg["start"], t["start"])
            if overlap > best_overlap:
                best_overlap = overlap
                best_turn = t
        if best_turn is None:
            mid = (seg["start"] + seg["end"]) / 2
            best_turn = min(turns, key=lambda t: abs((t["start"] + t["end"]) / 2 - mid))

        raw = best_turn["speaker"]
        if raw not in raw_to_friendly:
            raw_to_friendly[raw] = f"Speaker {next_index}"
            next_index += 1
        labeled.append({**seg, "speaker": raw_to_friendly[raw]})
    return labeled


def process_job(job_id: str, video_path: Path, model_size: str, target_lang: Optional[str], diarize: bool,
                 source_lang: Optional[str] = None, subtitle_mode: str = "hardsub"):
    job_dir = video_path.parent
    audio_path = job_dir / "audio.wav"
    srt_path = job_dir / "subtitles.srt"
    output_path = job_dir / ("output.mkv" if subtitle_mode == "softsub" else "output.mp4")
    transcript_raw_path = job_dir / "transcript_raw.txt"
    transcript_path = job_dir / "transcript.txt"

    with PROCESSING_LOCK:
        _process_job_locked(
            job_id, video_path, audio_path, srt_path, output_path,
            transcript_raw_path, transcript_path, model_size, target_lang, diarize, source_lang, subtitle_mode,
        )


def _process_job_locked(
    job_id, video_path, audio_path, srt_path, output_path,
    transcript_raw_path, transcript_path, model_size, target_lang, diarize, source_lang, subtitle_mode,
):
    try:
        check_cancelled(job_id)
        if diarize:
            # Fail fast on a missing HF token (or other engine misconfiguration)
            # before spending minutes transcribing - diarize() would raise the
            # same error anyway, but only after transcription already finished.
            get_diarization_engine().check_available()
        update_job(job_id, status="extracting_audio", percent=5, processing_started_at=time.time())
        extract_audio(job_id, video_path, audio_path)

        check_cancelled(job_id)
        update_job(job_id, status="transcribing", percent=10)
        transcribe_end = 50 if diarize else 60
        asr = get_asr_engine()
        segments, detected_lang = asr.transcribe(job_id, audio_path, model_size, percent_end=transcribe_end,
                                                  source_lang=source_lang)
        update_job(job_id, detected_language=detected_lang)

        if diarize:
            check_cancelled(job_id)
            update_job(job_id, status="diarizing", percent=transcribe_end)
            diarizer = get_diarization_engine()
            turns = diarizer.diarize(audio_path)
            segments = assign_speakers(segments, turns)
            speakers = sorted(
                {s["speaker"] for s in segments if s.get("speaker")},
                key=lambda s: int(s.rsplit(" ", 1)[-1]),
            )
            update_job(job_id, speakers=speakers, speaker_names={s: s for s in speakers}, percent=60)

        write_srt(segments, srt_path)

        subtitle_segments = segments
        if target_lang:
            # Always route every segment through per-segment language
            # detection, even when target_lang == detected_lang: the file's
            # overall detected language doesn't mean every segment is
            # actually in that language (foreign-language passages, or
            # Whisper's occasional stray hallucinated-English segment) - this
            # is what normalizes those to the target language too instead of
            # leaving them untouched.
            update_job(job_id, status="translating", percent=60)
            translator = get_translation_engine()
            subtitle_segments = translator.translate_segments(job_id, segments, detected_lang, target_lang)
            write_srt(subtitle_segments, srt_path)

        transcript_text = build_transcript(subtitle_segments)
        transcript_raw_path.write_text(transcript_text, encoding="utf-8")
        transcript_path.write_text(transcript_text, encoding="utf-8")

        check_cancelled(job_id)
        if subtitle_mode == "softsub":
            update_job(job_id, status="muxing_subtitles", percent=75)
            mux_softsub(job_id, video_path, srt_path, output_path)
        else:
            update_job(job_id, status="burning_in", percent=75)
            burn_subtitles(job_id, video_path, srt_path, output_path)

        # The output is complete and valid at this point - mark the job done
        # before best-effort cleanup, so a cleanup hiccup (e.g. Windows still
        # briefly holding a lock on a file ffmpeg just closed) never turns a
        # successful job into a false "error" and orphans a good result.
        update_job(job_id, status="done", percent=100)
    except JobCancelled:
        log.info("Job %s cancelled", job_id)
        update_job(job_id, status="cancelled", error=None)
        unregister_proc(job_id)
        for p in (audio_path, srt_path, output_path, video_path, transcript_raw_path, transcript_path):
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass
        return
    except Exception as e:
        log.exception("Job %s failed", job_id)
        update_job(job_id, status="error", error=str(e))
        return

    for p in (audio_path, srt_path, video_path):
        for attempt in range(5):
            try:
                p.unlink(missing_ok=True)
                break
            except PermissionError:
                time.sleep(0.5)
        else:
            log.warning("Could not delete leftover file %s after job %s completed", p, job_id)
