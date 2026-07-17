import logging
import os

import config as appconfig
from subburn.engines.base import DiarizationEngine
from subburn.engines.registry import register_diarization_engine
from subburn.models.cache import ModelCache

log = logging.getLogger("subburn")

_CACHE_KEY = "default"


class PyannoteDiarizationEngine(DiarizationEngine):
    def __init__(self):
        self._cache = ModelCache()

    def _load_pipeline(self):
        token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")
        if not token:
            raise RuntimeError(
                "Speaker diarization requires a Hugging Face access token. Create a free account at "
                "huggingface.co, accept the terms on the model pages at "
                "huggingface.co/pyannote/speaker-diarization-3.1, huggingface.co/pyannote/segmentation-3.0, and "
                "huggingface.co/pyannote/speaker-diarization-community-1, generate a token at "
                "huggingface.co/settings/tokens, then set it as the HF_TOKEN environment variable before "
                "starting this server."
            )

        from pyannote.audio import Pipeline

        pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", token=token)

        device_used = "cpu"
        if not appconfig.load().get("force_cpu"):
            try:
                import torch
                if torch.cuda.is_available():
                    pipeline = pipeline.to(torch.device("cuda"))
                    device_used = "cuda"
            except Exception as e:
                log.warning("Could not move diarization pipeline to GPU (%s); using CPU", e)

        log.info("Loaded pyannote speaker-diarization-3.1 pipeline on %s", device_used)
        return pipeline

    def _get_pipeline(self):
        return self._cache.get_or_load(_CACHE_KEY, self._load_pipeline)

    def diarize(self, audio_path) -> list[dict]:
        import soundfile as sf
        import torch

        pipeline = self._get_pipeline()
        data, sample_rate = sf.read(str(audio_path), dtype="float32", always_2d=True)
        waveform = torch.from_numpy(data.T)

        try:
            output = pipeline({"waveform": waveform, "sample_rate": sample_rate})
        except RuntimeError as e:
            if "CUDA" not in str(e).upper():
                raise
            log.warning("GPU diarization failed at runtime (%s); retrying on CPU", e)
            pipeline = pipeline.to(torch.device("cpu"))
            self._cache.set(_CACHE_KEY, pipeline)
            output = pipeline({"waveform": waveform, "sample_rate": sample_rate})

        # exclusive_speaker_diarization has no overlapping speech turns, which is
        # what we want when aligning against whisper's (non-overlapping) segments.
        annotation = output.exclusive_speaker_diarization

        turns = []
        for turn, _, speaker in annotation.itertracks(yield_label=True):
            turns.append({"start": turn.start, "end": turn.end, "speaker": speaker})
        return turns

    def is_loaded(self) -> bool:
        return self._cache.peek(_CACHE_KEY) is not None

    def unload(self) -> bool:
        return bool(self._cache.evict(_CACHE_KEY))


register_diarization_engine("pyannote", PyannoteDiarizationEngine())
