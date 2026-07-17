from fastapi import APIRouter, Depends

from subburn.logging_setup import get_log_lines
from subburn.web.auth import require_auth

router = APIRouter(prefix="/api/logs", dependencies=[Depends(require_auth)])


@router.get("")
async def get_logs(since: int = 0):
    return get_log_lines(since)
