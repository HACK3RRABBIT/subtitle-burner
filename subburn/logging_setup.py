import logging
import threading
from collections import deque

# In-memory ring buffer of recent log lines, exposed via /api/logs so the web
# UI can show what the backend is doing (crashes, warnings, ffmpeg/model
# messages) without needing terminal access - useful since this often runs
# headless behind the exe launcher's console window. Bounded so a long
# session can't grow this unboundedly.
LOG_BUFFER: deque = deque(maxlen=2000)
LOG_BUFFER_LOCK = threading.Lock()


class _BufferHandler(logging.Handler):
    def emit(self, record):
        msg = self.format(record)
        with LOG_BUFFER_LOCK:
            LOG_BUFFER.append(msg)


def setup_logging():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    buffer_handler = _BufferHandler()
    buffer_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logging.getLogger().addHandler(buffer_handler)
    # uvicorn configures its own loggers with propagate=False, so they need the
    # handler attached directly; "uvicorn.access" is deliberately excluded here -
    # per-request lines from the 2s job-status polling would drown out anything
    # actually useful (errors, startup messages, ffmpeg/model warnings).
    logging.getLogger("uvicorn.error").addHandler(buffer_handler)


def get_log_lines(since: int = 0) -> dict:
    with LOG_BUFFER_LOCK:
        lines = list(LOG_BUFFER)
    # `since` is the line count the caller already has, so it only needs to
    # request/render what's new each poll instead of the whole buffer.
    return {"lines": lines[since:], "total": len(lines)}
