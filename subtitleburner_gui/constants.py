# Mirrors web/src/app/page.js's constants, so the native GUI and web UI offer
# the same choices/wording. Kept here (not re-derived from the web UI) since
# there's no shared source between a React app and a Qt app.

STATUS_LABELS = {
    "queued": "Queued...",
    "extracting_audio": "Extracting audio...",
    "transcribing": "Transcribing speech...",
    "diarizing": "Identifying speakers...",
    "translating": "Translating subtitles...",
    "burning_in": "Burning subtitles into video...",
    "muxing_subtitles": "Embedding subtitle track...",
    "cancelling": "Cancelling...",
    "cancelled": "Cancelled",
    "done": "Done!",
    "error": "Failed",
}

MODEL_HINTS = {
    "tiny": "fastest, least accurate",
    "tiny.en": "fastest, least accurate (English only)",
    "base": "fast",
    "base.en": "fast (English only)",
    "small": "balanced (recommended)",
    "small.en": "balanced (English only)",
    "medium": "slower, more accurate",
    "medium.en": "slower, more accurate (English only)",
    "large-v1": "large model, v1",
    "large-v2": "large model, v2, more accurate than v1",
    "large-v3": "large model, v3, most accurate",
    "large": "alias for the latest large model",
    "distil-large-v2": "distilled large-v2, much faster, nearly as accurate",
    "distil-medium.en": "distilled medium, faster (English only)",
    "distil-small.en": "distilled small, faster (English only)",
    "distil-large-v3": "distilled large-v3, much faster, nearly as accurate",
    "distil-large-v3.5": "distilled large-v3.5, much faster, nearly as accurate",
    "large-v3-turbo": "large-v3 turbo, fast + accurate",
    "turbo": "alias for the latest turbo model",
}

# Persian first since that's this app's primary focus.
LANGUAGES = [
    ("fa", "Persian (فارسی)"),
    ("en", "English"),
    ("es", "Spanish"),
    ("fr", "French"),
    ("de", "German"),
    ("it", "Italian"),
    ("pt", "Portuguese"),
    ("ru", "Russian"),
    ("zh", "Chinese"),
    ("ja", "Japanese"),
    ("ko", "Korean"),
    ("ar", "Arabic"),
    ("tr", "Turkish"),
    ("hi", "Hindi"),
]


def model_label(model_size: str) -> str:
    hint = MODEL_HINTS.get(model_size)
    return f"{model_size} — {hint}" if hint else model_size


def format_eta(seconds) -> str:
    if seconds is None:
        return ""
    if seconds < 5:
        return "almost done"
    if seconds < 60:
        return f"about {round(seconds)}s left"
    minutes = round(seconds / 60)
    if minutes < 60:
        return f"about {minutes}m left"
    hours, mins = divmod(minutes, 60)
    return f"about {hours}h {mins}m left"


def format_bytes(num_bytes) -> str:
    if not num_bytes:
        return ""
    units = ["B", "KB", "MB", "GB"]
    n = float(num_bytes)
    i = 0
    while n >= 1024 and i < len(units) - 1:
        n /= 1024
        i += 1
    return f"{n:.0f} {units[i]}" if (n >= 10 or i == 0) else f"{n:.1f} {units[i]}"
