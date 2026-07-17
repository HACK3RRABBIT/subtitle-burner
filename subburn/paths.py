from pathlib import Path

# app.py is the entry point one directory above this package, so its parent
# is the actual project/install root - not Path(__file__).parent, which
# would resolve to inside subburn/ itself.
BASE_DIR = Path(__file__).parent.parent
JOBS_DIR = BASE_DIR / "jobs"
JOBS_DIR.mkdir(exist_ok=True)
