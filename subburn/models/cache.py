import logging
import threading
from typing import Any, Callable, Optional

log = logging.getLogger("subburn")


def _free_memory():
    import gc
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


class ModelCache:
    """Single-slot-eviction cache for a heavy resident model (a whisper model
    keyed by size, a diarization pipeline keyed by a fixed name, etc).

    Only one entry is ever kept: loading a different key evicts whatever was
    cached first and frees GPU/host memory. Jobs are already serialized
    (PROCESSING_LOCK), so there's never a need to keep more than one heavy
    model resident at a time - keeping every distinct key ever requested
    cached forever was the cause of a real CUDA-OOM bug (a second, larger
    whisper model failed to load on GPU because an earlier one was still
    resident), so this eviction is load-bearing behavior, not just tidiness.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._items: dict[str, Any] = {}

    def get_or_load(self, key: str, loader: Callable[[], Any]) -> Any:
        with self._lock:
            if key in self._items:
                return self._items[key]

            if self._items:
                log.info("Evicting cached model(s) %s to free memory for '%s'", list(self._items.keys()), key)
                self._items.clear()
                _free_memory()

            value = loader()
            self._items[key] = value
            return value

    def set(self, key: str, value: Any):
        with self._lock:
            self._items[key] = value

    def peek(self, key: str) -> Optional[Any]:
        """Reads the cache without loading - safe to call from a passive
        status check (e.g. GET /api/models/loaded) since it never triggers a
        multi-GB model load as a side effect of an otherwise-read-only poll."""
        with self._lock:
            return self._items.get(key)

    def keys(self) -> list[str]:
        with self._lock:
            return list(self._items.keys())

    def items(self) -> dict[str, Any]:
        """Atomic copy of everything currently cached - for passive
        introspection (never triggers a load)."""
        with self._lock:
            return dict(self._items)

    def evict(self, key: Optional[str] = None) -> list[str]:
        """Evicts one key, or everything if key is None. Returns what was
        actually evicted."""
        with self._lock:
            if key is None:
                evicted = list(self._items.keys())
                self._items.clear()
            else:
                evicted = [key] if key in self._items else []
                self._items.pop(key, None)
            if evicted:
                _free_memory()
            return evicted
