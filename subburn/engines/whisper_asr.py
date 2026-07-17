import logging

import config as appconfig
from subburn.core.jobs import JobCancelled, check_cancelled, update_job
from subburn.engines.base import ASREngine
from subburn.engines.registry import register_asr_engine
from subburn.models.cache import ModelCache

log = logging.getLogger("subburn")


class WhisperASREngine(ASREngine):
    """faster-whisper backed ASR engine. Loads (and caches) a model,
    preferring CUDA/float16 and falling back to CPU/int8 if CUDA or the
    required cuDNN/cuBLAS DLLs aren't usable."""

    def __init__(self):
        self._cache = ModelCache()

    def _load_model(self, model_size: str):
        from faster_whisper import WhisperModel

        if appconfig.load().get("force_cpu"):
            model = WhisperModel(model_size, device="cpu", compute_type="int8")
            device_used = "cpu (int8, forced)"
        else:
            try:
                model = WhisperModel(model_size, device="cuda", compute_type="float16")
                device_used = "cuda (float16)"
            except Exception as e:
                log.warning("CUDA load failed for model '%s' (%s); falling back to CPU", model_size, e)
                model = WhisperModel(model_size, device="cpu", compute_type="int8")
                device_used = "cpu (int8)"

        log.info("Loaded whisper model '%s' on %s", model_size, device_used)
        return model, device_used

    def _get_model(self, model_size: str):
        # get_or_load evicts any other cached model size first - only one job
        # runs at a time (PROCESSING_LOCK serializes them), so there's never a
        # need to keep more than one whisper model resident. Without this,
        # every distinct model_size ever requested stays cached (and its VRAM
        # reserved) forever - which starves later loads of a *different* size,
        # causing a CUDA OOM that then falls back to CPU and can fail there too
        # on a memory-constrained machine.
        return self._cache.get_or_load(model_size, lambda: self._load_model(model_size))

    def transcribe(self, job_id, audio_path, model_size, percent_end=60, source_lang=None):
        model, device_used = self._get_model(model_size)
        update_job(job_id, device_used=device_used)

        def run(m):
            # Whisper's auto language-detection only looks at the first ~30s and can
            # misfire; separately, several non-English languages (Persian included)
            # are prone to the model spontaneously translating to English even with
            # task="transcribe" if it isn't told what language to expect. Passing
            # the known source language explicitly avoids both failure modes.
            #
            # Podcasts that mix in chanted/recited passages (e.g. Arabic prayers
            # inside a Persian podcast) trip Whisper's default hallucination
            # guards - repetitive, melismatic delivery reads as a high compression
            # ratio and can spike its "no speech" probability - causing those
            # stretches to be silently dropped with no subtitle at all. Loosening
            # these thresholds keeps that content instead of discarding it, and
            # disabling condition_on_previous_text stops a rough patch (e.g. a
            # sudden language switch) from degrading the segments after it.
            segments_gen, info = m.transcribe(
                str(audio_path), language=source_lang, task="transcribe",
                condition_on_previous_text=False,
                no_speech_threshold=0.8,
                compression_ratio_threshold=3.0,
                log_prob_threshold=-1.5,
            )
            segs = []
            duration = info.duration or 1.0
            for seg in segments_gen:
                check_cancelled(job_id)
                segs.append({"start": seg.start, "end": seg.end, "text": seg.text})
                percent = 10 + int(min(seg.end / duration, 1.0) * (percent_end - 10))
                update_job(job_id, percent=percent)
            return segs, info.language

        try:
            return run(model)
        except JobCancelled:
            raise
        except Exception as e:
            if device_used.startswith("cuda"):
                log.warning("CUDA transcription failed at runtime (%s); reloading model on CPU", e)
                from faster_whisper import WhisperModel

                model = WhisperModel(model_size, device="cpu", compute_type="int8")
                self._cache.set(model_size, (model, "cpu (int8, fallback)"))
                update_job(job_id, device_used="cpu (int8, fallback)")
                return run(model)
            raise

    def list_available_models(self) -> list[str]:
        from faster_whisper.utils import available_models
        return sorted(available_models())

    def get_loaded(self) -> list[dict]:
        return [{"model_size": size, "device": device} for size, (_, device) in self._cache.items().items()]

    def unload(self) -> list[str]:
        return self._cache.evict()


register_asr_engine("faster-whisper", WhisperASREngine())
