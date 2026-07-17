import logging

from fastapi import APIRouter, Depends, HTTPException

from subburn.core.jobs import PROCESSING_LOCK
from subburn.engines.registry import get_asr_engine, get_diarization_engine
from subburn.web.auth import require_auth

log = logging.getLogger("subburn")

router = APIRouter(prefix="/api/models", dependencies=[Depends(require_auth)])


@router.get("")
async def list_models():
    return {"models": sorted(get_asr_engine().list_available_models())}


@router.get("/loaded")
async def get_loaded_models():
    return {
        "whisper_models": get_asr_engine().get_loaded(),
        "diarization_loaded": get_diarization_engine().is_loaded(),
    }


@router.post("/unload")
async def unload_models():
    if not PROCESSING_LOCK.acquire(blocking=False):
        raise HTTPException(409, "A job is currently processing; can't unload models right now.")
    try:
        unloaded_whisper = get_asr_engine().unload()
        unloaded_diarization = get_diarization_engine().unload()
        log.info("Unloaded models on request: whisper=%s diarization=%s", unloaded_whisper, unloaded_diarization)
        return {"unloaded_whisper_models": unloaded_whisper, "unloaded_diarization": unloaded_diarization}
    finally:
        PROCESSING_LOCK.release()
