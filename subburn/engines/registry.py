from subburn.engines.base import ASREngine, DiarizationEngine, TranslationEngine

_asr_engines: dict[str, ASREngine] = {}
_translation_engines: dict[str, TranslationEngine] = {}
_diarization_engines: dict[str, DiarizationEngine] = {}

DEFAULT_ASR_ENGINE = "faster-whisper"
DEFAULT_TRANSLATION_ENGINE = "argos"
DEFAULT_DIARIZATION_ENGINE = "pyannote"


def register_asr_engine(name: str, engine: ASREngine):
    _asr_engines[name] = engine


def get_asr_engine(name: str = DEFAULT_ASR_ENGINE) -> ASREngine:
    return _asr_engines[name]


def list_asr_engines() -> dict[str, ASREngine]:
    return dict(_asr_engines)


def register_translation_engine(name: str, engine: TranslationEngine):
    _translation_engines[name] = engine


def get_translation_engine(name: str = DEFAULT_TRANSLATION_ENGINE) -> TranslationEngine:
    return _translation_engines[name]


def list_translation_engines() -> dict[str, TranslationEngine]:
    return dict(_translation_engines)


def register_diarization_engine(name: str, engine: DiarizationEngine):
    _diarization_engines[name] = engine


def get_diarization_engine(name: str = DEFAULT_DIARIZATION_ENGINE) -> DiarizationEngine:
    return _diarization_engines[name]


def list_diarization_engines() -> dict[str, DiarizationEngine]:
    return dict(_diarization_engines)
