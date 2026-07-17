from subburn.logging_setup import setup_logging

setup_logging()  # first, so no early startup log line is dropped before the buffer handler exists

from subburn.bootstrap_env import bootstrap_environment  # noqa: E402

bootstrap_environment()

import subburn.engines  # noqa: E402,F401 - registers faster-whisper/argos/pyannote as a side effect

from fastapi import FastAPI  # noqa: E402

import config as appconfig  # noqa: E402
from subburn.media.ffmpeg import check_ffmpeg  # noqa: E402
from subburn.web.auth import router as auth_router  # noqa: E402
from subburn.web.routes import api_router  # noqa: E402

app = FastAPI(title="Subtitle Burner")
app.include_router(auth_router)
app.include_router(api_router)
app.on_event("startup")(check_ffmpeg)

if __name__ == "__main__":
    import uvicorn

    # 0.0.0.0 so other devices on the same LAN/Wi-Fi (phone, etc.) can reach
    # this too, not just this machine. Windows Firewall still has to allow the
    # port for that to actually work - see the console output below.
    uvicorn.run(app, host="0.0.0.0", port=appconfig.load().get("port", 8000))
