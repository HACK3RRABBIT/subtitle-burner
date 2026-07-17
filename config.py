import json
import threading
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config.json"

DEFAULTS = {
    "hf_token": "",
    "default_model": "small",
    "default_lang": "",
    "default_source_lang": "",
    "force_cpu": False,
    "port": 8000,
    "app_password": "",
}

_lock = threading.Lock()


def load() -> dict:
    with _lock:
        if not CONFIG_PATH.exists():
            return dict(DEFAULTS)
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return dict(DEFAULTS)
        merged = dict(DEFAULTS)
        merged.update({k: v for k, v in data.items() if k in DEFAULTS})
        return merged


def save(updates: dict) -> dict:
    with _lock:
        current = dict(DEFAULTS)
        if CONFIG_PATH.exists():
            try:
                current.update({k: v for k, v in json.loads(CONFIG_PATH.read_text(encoding="utf-8")).items() if k in DEFAULTS})
            except (json.JSONDecodeError, OSError):
                pass
        current.update({k: v for k, v in updates.items() if k in DEFAULTS})
        CONFIG_PATH.write_text(json.dumps(current, indent=2), encoding="utf-8")
        return current
