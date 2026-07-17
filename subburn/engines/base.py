from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional


class ASREngine(ABC):
    @abstractmethod
    def transcribe(self, job_id: str, audio_path: Path, model_size: str, percent_end: int = 60,
                   source_lang: Optional[str] = None) -> tuple[list[dict], str]:
        """Returns (segments, detected_language)."""
        ...

    @abstractmethod
    def list_available_models(self) -> list[str]:
        ...

    def get_loaded(self) -> list[dict]:
        """Passive introspection of what's currently resident (e.g. for a
        status endpoint) - must never trigger a load itself. Default: this
        engine doesn't cache anything locally."""
        return []

    def unload(self) -> list[str]:
        """Frees any resident model(s); returns what was freed. Default:
        nothing to free."""
        return []


class TranslationEngine(ABC):
    @abstractmethod
    def translate_segments(self, job_id: str, segments: list[dict], from_code: str, to_code: str) -> list[dict]:
        ...


class DiarizationEngine(ABC):
    @abstractmethod
    def diarize(self, audio_path: Path) -> list[dict]:
        """Returns speaker turns: [{"start": .., "end": .., "speaker": ..}, ...]."""
        ...

    def is_loaded(self) -> bool:
        """Passive introspection - must never trigger a load. Default: this
        engine doesn't cache anything locally."""
        return False

    def unload(self) -> bool:
        """Returns whether anything was actually unloaded."""
        return False
