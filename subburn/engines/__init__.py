# Importing these registers each engine's default instance in the registry
# (registration is a module-level side effect - see the register_*_engine()
# call at the bottom of each). app.py just does `import subburn.engines` once
# to load every built-in engine; this is also the natural seam for a future
# external-plugin loader to extend (scan a plugins directory and import those
# too, without app.py needing to change).
from subburn.engines import argos_translation, pyannote_diarization, whisper_asr  # noqa: F401
