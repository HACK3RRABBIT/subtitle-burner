from pathlib import Path
from typing import Optional

import httpx


class AuthRequiredError(Exception):
    """Raised when the backend returns 401 - the app_password protecting this
    instance (meant for LAN/web access) also gates the native client, since
    require_auth doesn't distinguish "local first-party GUI" from anyone
    else. Callers surface this as a login prompt, then retry."""


class ApiClient:
    """Thin synchronous wrapper around the same HTTP API tui.py and the web
    UI already use. Methods are blocking (httpx) - callers run them off the
    Qt main thread via workers.run_in_thread, never call these directly from
    a slot that must stay responsive.

    httpx.Client keeps its own cookie jar, so a successful login() persists
    the session cookie for every later call on this same instance.
    """

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(base_url=self.base_url, timeout=30.0)

    def close(self):
        self.client.close()

    def _check(self, res: httpx.Response) -> httpx.Response:
        if res.status_code == 401:
            raise AuthRequiredError()
        res.raise_for_status()
        return res

    def login(self, password: str) -> bool:
        res = self.client.post("/api/auth/login", json={"password": password})
        return res.status_code == 200

    def auth_status(self) -> dict:
        return self._check(self.client.get("/api/auth/status")).json()

    def list_models(self) -> list[str]:
        return self._check(self.client.get("/api/models")).json().get("models", [])

    def get_settings(self) -> dict:
        return self._check(self.client.get("/api/settings")).json()

    def update_settings(self, body: dict) -> dict:
        return self._check(self.client.post("/api/settings", json=body)).json()

    def get_loaded_models(self) -> dict:
        return self._check(self.client.get("/api/models/loaded")).json()

    def unload_models(self) -> dict:
        return self._check(self.client.post("/api/models/unload")).json()

    def create_job(self, video_path: str, model_size: str, source_lang: str, target_lang: str,
                   diarize: bool, subtitle_mode: str) -> str:
        path = Path(video_path)
        with open(path, "rb") as f:
            res = self.client.post(
                "/api/jobs",
                data={
                    "model_size": model_size,
                    "source_lang": source_lang,
                    "target_lang": target_lang,
                    "diarize": "true" if diarize else "false",
                    "subtitle_mode": subtitle_mode,
                },
                files={"video": (path.name, f, "application/octet-stream")},
                timeout=None,
            )
        return self._check(res).json()["job_id"]

    def get_job(self, job_id: str) -> dict:
        return self._check(self.client.get(f"/api/jobs/{job_id}")).json()

    def cancel_job(self, job_id: str):
        res = self.client.post(f"/api/jobs/{job_id}/cancel")
        if res.status_code == 409:
            return  # already done/error/cancelled - not a real failure
        self._check(res)

    def get_transcript(self, job_id: str) -> str:
        return self._check(self.client.get(f"/api/jobs/{job_id}/transcript")).text

    def rename_speakers(self, job_id: str, names: dict) -> dict:
        return self._check(self.client.post(f"/api/jobs/{job_id}/speakers", json={"names": names})).json()

    def get_logs(self, since: int = 0) -> dict:
        return self._check(self.client.get("/api/logs", params={"since": since})).json()

    def download_url(self, job_id: str) -> str:
        return f"{self.base_url}/api/jobs/{job_id}/download"

    def download_to(self, job_id: str, dest_path: str) -> None:
        with self.client.stream("GET", f"/api/jobs/{job_id}/download") as res:
            self._check(res)
            with open(dest_path, "wb") as f:
                for chunk in res.iter_bytes():
                    f.write(chunk)
