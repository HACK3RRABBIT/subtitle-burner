from pathlib import Path
from typing import Optional

import httpx

import launcher

BASE_DIR = launcher.BASE_DIR
JOBS_DIR = BASE_DIR / "jobs"

# Mirrors web/src/app/page.js's LANGUAGES list, so the TUI and web UI offer
# the same source/target language choices.
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

STATUS_LABELS = {
    "queued": "Queued...",
    "extracting_audio": "Extracting audio...",
    "transcribing": "Transcribing speech...",
    "diarizing": "Identifying speakers...",
    "translating": "Translating subtitles...",
    "burning_in": "Burning subtitles into video...",
    "muxing_subtitles": "Embedding subtitle track...",
    "cancelling": "Cancelling...",
    "cancelled": "Cancelled.",
    "done": "Done!",
    "error": "Failed.",
}


from textual import work  # noqa: E402
from textual.app import App, ComposeResult  # noqa: E402
from textual.containers import Horizontal, Vertical, VerticalScroll  # noqa: E402
from textual.widgets import (  # noqa: E402
    Button,
    DirectoryTree,
    Footer,
    Header,
    Input,
    Label,
    ProgressBar,
    RadioButton,
    RadioSet,
    Select,
    Static,
    Switch,
)


class SubtitleBurnerTUI(App):
    CSS = """
    Screen { layout: vertical; }
    #form { padding: 1 2; }
    #progress_area { padding: 1 2; display: none; }
    #progress_area.visible { display: block; }
    #form.hidden { display: none; }
    .field { margin-bottom: 1; }
    .field Label { margin-bottom: 0; color: $text-muted; }
    #browser { height: 12; border: round $primary; margin-bottom: 1; }
    #status_line { margin-top: 1; }
    #error_line { color: $error; margin-top: 1; }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("u", "unload_models", "Unload models"),
    ]

    def __init__(self):
        super().__init__()
        self.base_url = ""
        self.backend_proc = None
        self.current_job_id: Optional[str] = None
        self.current_subtitle_mode = "hardsub"
        self.poll_timer = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with VerticalScroll(id="form"):
            yield Static("[b]Video file[/b]")
            with Vertical(classes="field"):
                yield Input(placeholder="Full path to a video file", id="video_path")
                yield DirectoryTree(str(Path.home()), id="browser")

            with Horizontal(classes="field"):
                with Vertical():
                    yield Label("Whisper model")
                    yield Select([], id="model_size", allow_blank=True)
                with Vertical():
                    yield Label("Spoken language")
                    yield Select(
                        [("Auto-detect", "")] + LANGUAGES, id="source_lang", value="", allow_blank=False
                    )
                with Vertical():
                    yield Label("Subtitle language")
                    yield Select(
                        [("No translation", "")] + LANGUAGES, id="target_lang", value="", allow_blank=False
                    )

            with Horizontal(classes="field"):
                yield Label("Separate speakers")
                yield Switch(id="diarize")

            with Vertical(classes="field"):
                yield Label("Subtitle delivery")
                with RadioSet(id="subtitle_mode"):
                    yield RadioButton("Hardsub (burned in)", value=True, id="hardsub")
                    yield RadioButton("Softsub (selectable track)", id="softsub")

            yield Button("Upload & Process", id="submit", variant="primary")
            yield Static("", id="error_line")

        with Vertical(id="progress_area"):
            yield Label("", id="status_line")
            yield ProgressBar(total=100, id="progress_bar")
            with Horizontal():
                yield Button("Cancel", id="cancel", variant="warning")
                yield Button("Process another file", id="restart", variant="primary")
            yield Static("", id="result_line")
        yield Footer()

    async def on_mount(self):
        self.query_one("#restart", Button).display = False
        self.query_one("#cancel", Button).display = False
        self.title = "Subtitle Burner"
        self.sub_title = "Starting backend..."
        self.start_backend()

    @work(thread=True)
    def start_backend(self):
        import subprocess

        port = launcher.get_backend_port()
        self.base_url = f"http://127.0.0.1:{port}"
        try:
            httpx.get(f"{self.base_url}/api/models", timeout=2)
        except Exception:
            try:
                launcher.run_bootstrap_if_needed()
            except subprocess.CalledProcessError as e:
                self.call_from_thread(self.set_error, f"First-time setup failed: {e}")
                return
            self.backend_proc = subprocess.Popen(
                [str(launcher.PYTHON_EXECUTABLE), "-u", str(launcher.APP_SCRIPT)],
                cwd=str(BASE_DIR),
                env=launcher.child_env(),
            )
            if not launcher.wait_for_http(f"{self.base_url}/api/models", timeout=180):
                self.call_from_thread(self.set_error, "Backend did not start in time.")
                return
        self.call_from_thread(self.on_backend_ready)

    def on_backend_ready(self):
        self.sub_title = "Ready"
        self.load_models()

    @work
    async def load_models(self):
        async with httpx.AsyncClient() as client:
            try:
                res = await client.get(f"{self.base_url}/api/models")
                models = res.json().get("models", [])
            except Exception:
                models = ["small"]
        select = self.query_one("#model_size", Select)
        select.set_options([(m, m) for m in models])
        if "small" in models:
            select.value = "small"
        elif models:
            select.value = models[0]

    def set_error(self, message: str):
        self.query_one("#error_line", Static).update(message)

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected):
        self.query_one("#video_path", Input).value = str(event.path)

    async def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "submit":
            await self.submit_job()
        elif event.button.id == "cancel":
            await self.cancel_job()
        elif event.button.id == "restart":
            self.reset_form()

    async def submit_job(self):
        self.set_error("")
        path_str = self.query_one("#video_path", Input).value.strip()
        if not path_str:
            self.set_error("Enter or pick a video file path first.")
            return
        video_path = Path(path_str)
        if not video_path.is_file():
            self.set_error(f"File not found: {video_path}")
            return

        model_size = self.query_one("#model_size", Select).value
        source_lang = self.query_one("#source_lang", Select).value or ""
        target_lang = self.query_one("#target_lang", Select).value or ""
        diarize = self.query_one("#diarize", Switch).value
        subtitle_mode = "softsub" if self.query_one("#subtitle_mode", RadioSet).pressed_button.id == "softsub" else "hardsub"
        self.current_subtitle_mode = subtitle_mode

        self.query_one("#submit", Button).disabled = True
        self.set_error("Uploading...")
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                with open(video_path, "rb") as f:
                    res = await client.post(
                        f"{self.base_url}/api/jobs",
                        data={
                            "model_size": model_size,
                            "source_lang": source_lang,
                            "target_lang": target_lang,
                            "diarize": "true" if diarize else "false",
                            "subtitle_mode": subtitle_mode,
                        },
                        files={"video": (video_path.name, f, "application/octet-stream")},
                    )
            if res.status_code != 200:
                self.set_error(f"Upload failed ({res.status_code}): {res.text[:200]}")
                self.query_one("#submit", Button).disabled = False
                return
            self.current_job_id = res.json()["job_id"]
        except Exception as e:
            self.set_error(f"Upload failed: {e}")
            self.query_one("#submit", Button).disabled = False
            return

        self.query_one("#form", VerticalScroll).add_class("hidden")
        self.query_one("#progress_area", Vertical).add_class("visible")
        self.query_one("#cancel", Button).display = True
        self.query_one("#restart", Button).display = False
        self.poll_timer = self.set_interval(1.5, self.poll_job)

    async def poll_job(self):
        if not self.current_job_id:
            return
        async with httpx.AsyncClient() as client:
            try:
                res = await client.get(f"{self.base_url}/api/jobs/{self.current_job_id}")
                job = res.json()
            except Exception:
                return

        pct = job.get("percent") or 0
        status = job.get("status")
        label = STATUS_LABELS.get(status, status)
        eta = job.get("eta_seconds")
        eta_text = f"  (~{int(eta)}s left)" if eta else ""
        self.query_one("#status_line", Label).update(f"{label}{eta_text}")
        self.query_one("#progress_bar", ProgressBar).update(progress=pct)

        if status in ("done", "error", "cancelled"):
            if self.poll_timer:
                self.poll_timer.stop()
            self.query_one("#cancel", Button).display = False
            self.query_one("#restart", Button).display = True
            if status == "done":
                ext = ".mkv" if self.current_subtitle_mode == "softsub" else ".mp4"
                output_path = JOBS_DIR / self.current_job_id / f"output{ext}"
                self.query_one("#result_line", Static).update(f"[b]Saved to:[/b] {output_path}")
            elif status == "error":
                self.query_one("#result_line", Static).update(f"[red]{job.get('error', 'Unknown error')}[/red]")
            else:
                self.query_one("#result_line", Static).update("Job cancelled.")

    async def cancel_job(self):
        if not self.current_job_id:
            return
        self.query_one("#cancel", Button).disabled = True
        async with httpx.AsyncClient() as client:
            try:
                await client.post(f"{self.base_url}/api/jobs/{self.current_job_id}/cancel")
            except Exception:
                pass

    def reset_form(self):
        self.current_job_id = None
        self.query_one("#submit", Button).disabled = False
        self.query_one("#cancel", Button).disabled = False
        self.query_one("#progress_bar", ProgressBar).update(progress=0)
        self.query_one("#result_line", Static).update("")
        self.query_one("#error_line", Static).update("")
        self.query_one("#progress_area", Vertical).remove_class("visible")
        self.query_one("#form", VerticalScroll).remove_class("hidden")

    @work
    async def action_unload_models(self):
        if not self.base_url:
            return
        async with httpx.AsyncClient() as client:
            try:
                await client.post(f"{self.base_url}/api/models/unload")
                self.sub_title = "Models unloaded"
            except Exception as e:
                self.sub_title = f"Unload failed: {e}"

    async def on_unmount(self):
        if self.backend_proc and self.backend_proc.poll() is None:
            self.backend_proc.terminate()


def main():
    SubtitleBurnerTUI().run()


if __name__ == "__main__":
    main()
