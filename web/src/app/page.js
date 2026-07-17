"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  UploadCloudIcon,
  SettingsIcon,
  DownloadIcon,
  CheckCircleIcon,
  AlertTriangleIcon,
  TerminalIcon,
  ChevronDownIcon,
  XIcon,
  LoaderIcon,
  MicIcon,
  UsersIcon,
  LogOutIcon,
  EjectIcon,
  CpuIcon,
} from "./icons";

const STATUS_LABELS = {
  queued: "Queued...",
  extracting_audio: "Extracting audio...",
  transcribing: "Transcribing speech...",
  diarizing: "Identifying speakers...",
  translating: "Translating subtitles...",
  burning_in: "Burning subtitles into video...",
  muxing_subtitles: "Embedding subtitle track...",
  cancelling: "Cancelling...",
  cancelled: "Cancelled",
  done: "Done!",
  error: "Failed",
};

// Friendly hints for well-known model names; any model faster-whisper adds in
// the future that we don't recognize still shows up (just without a hint).
const MODEL_HINTS = {
  tiny: "fastest, least accurate",
  "tiny.en": "fastest, least accurate (English only)",
  base: "fast",
  "base.en": "fast (English only)",
  small: "balanced (recommended)",
  "small.en": "balanced (English only)",
  medium: "slower, more accurate",
  "medium.en": "slower, more accurate (English only)",
  "large-v1": "large model, v1",
  "large-v2": "large model, v2, more accurate than v1",
  "large-v3": "large model, v3, most accurate",
  large: "alias for the latest large model",
  "distil-large-v2": "distilled large-v2, much faster, nearly as accurate",
  "distil-medium.en": "distilled medium, faster (English only)",
  "distil-small.en": "distilled small, faster (English only)",
  "distil-large-v3": "distilled large-v3, much faster, nearly as accurate",
  "distil-large-v3.5": "distilled large-v3.5, much faster, nearly as accurate",
  "large-v3-turbo": "large-v3 turbo, fast + accurate",
  turbo: "alias for the latest turbo model",
};

// Persian first since that's this app's primary focus; "Auto-detect" /
// "No translation" placeholders are prepended separately per-select since
// their wording differs between the source-language and target-language uses.
const LANGUAGES = [
  { code: "fa", label: "Persian (فارسی)" },
  { code: "en", label: "English" },
  { code: "es", label: "Spanish" },
  { code: "fr", label: "French" },
  { code: "de", label: "German" },
  { code: "it", label: "Italian" },
  { code: "pt", label: "Portuguese" },
  { code: "ru", label: "Russian" },
  { code: "zh", label: "Chinese" },
  { code: "ja", label: "Japanese" },
  { code: "ko", label: "Korean" },
  { code: "ar", label: "Arabic" },
  { code: "tr", label: "Turkish" },
  { code: "hi", label: "Hindi" },
];

function LangSelect({ id, value, onChange, placeholder, disabled }) {
  return (
    <select id={id} value={value} onChange={onChange} disabled={disabled}>
      <option value="">{placeholder}</option>
      {LANGUAGES.map(({ code, label }) => (
        <option key={code} value={code}>{label}</option>
      ))}
    </select>
  );
}

function Switch({ checked, onChange, disabled }) {
  return (
    <span className="switch">
      <input type="checkbox" checked={checked} onChange={onChange} disabled={disabled} />
      <span className="track" />
      <span className="thumb" />
    </span>
  );
}

function formatEta(seconds) {
  if (seconds == null) return "";
  if (seconds < 5) return "almost done";
  if (seconds < 60) return `about ${Math.round(seconds)}s left`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `about ${minutes}m left`;
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  return `about ${hours}h ${mins}m left`;
}

function formatBytes(bytes) {
  if (!bytes) return "";
  const units = ["B", "KB", "MB", "GB"];
  let i = 0;
  let n = bytes;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(n >= 10 || i === 0 ? 0 : 1)} ${units[i]}`;
}

// Any 401 from a protected endpoint means the session expired or auth was
// just turned on elsewhere - bounce to /login rather than showing a
// confusing generic error.
async function apiFetch(url, options) {
  const res = await fetch(url, options);
  if (res.status === 401) {
    window.location.href = "/login";
    throw new Error("Not authenticated");
  }
  return res;
}

function LogConsole() {
  const [lines, setLines] = useState([]);
  const totalRef = useRef(0);
  const bodyRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const res = await apiFetch(`/api/logs?since=${totalRef.current}`);
        if (!res.ok) return;
        const data = await res.json();
        if (cancelled || !data.lines?.length) return;
        totalRef.current = data.total;
        setLines((prev) => [...prev, ...data.lines].slice(-500));
      } catch {
        // Transient fetch failures are fine to just skip this tick.
      }
    };
    poll();
    const timer = setInterval(poll, 1500);
    return () => { cancelled = true; clearInterval(timer); };
  }, []);

  useEffect(() => {
    if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
  }, [lines]);

  return (
    <div className="log-console">
      <div className="log-console-head">
        <div className="log-console-title">
          <span className="log-console-dot" />
          Backend log
        </div>
      </div>
      <div className="log-console-body" ref={bodyRef}>
        {lines.length === 0 ? (
          <div className="log-console-empty">No log output yet.</div>
        ) : (
          lines.map((line, i) => {
            const cls = /\[ERROR]|Traceback/i.test(line)
              ? "lvl-error"
              : /\[WARNING]/i.test(line)
                ? "lvl-warning"
                : "";
            return <div className={`log-line ${cls}`} key={i}>{line}</div>;
          })
        )}
      </div>
    </div>
  );
}

export default function Home() {
  const router = useRouter();
  const fileInputRef = useRef(null);
  const pollTimerRef = useRef(null);

  const [authChecked, setAuthChecked] = useState(false);
  const [models, setModels] = useState([]);

  const [selectedFile, setSelectedFile] = useState(null);
  const [dragover, setDragover] = useState(false);

  const [modelSize, setModelSize] = useState("small");
  const [sourceLang, setSourceLang] = useState("");
  const [targetLang, setTargetLang] = useState("");
  const [diarize, setDiarize] = useState(false);
  const [subtitleMode, setSubtitleMode] = useState("hardsub");

  const [formDisabled, setFormDisabled] = useState(false);
  const [progressVisible, setProgressVisible] = useState(false);
  const [jobStatus, setJobStatus] = useState("");
  const [progressStatus, setProgressStatus] = useState("Queued...");
  const [progressPercent, setProgressPercent] = useState(0);
  const [progressEta, setProgressEta] = useState("");
  const [jobDone, setJobDone] = useState(false);

  const [currentJobId, setCurrentJobId] = useState(null);
  const [downloadReady, setDownloadReady] = useState(false);
  const [resultSubtitleMode, setResultSubtitleMode] = useState("hardsub");
  const [transcript, setTranscript] = useState(null);
  const [speakers, setSpeakers] = useState([]);
  const [speakerInputs, setSpeakerInputs] = useState({});
  const [errorMessage, setErrorMessage] = useState("");

  const [settingsOpen, setSettingsOpen] = useState(false);
  const [logsOpen, setLogsOpen] = useState(false);
  const [hfTokenSet, setHfTokenSet] = useState(false);
  const [appPasswordSet, setAppPasswordSet] = useState(false);
  const [setHfToken, setSetHfToken] = useState("");
  const [setAppPassword, setSetAppPassword] = useState("");
  const [setDefaultModel, setSetDefaultModel] = useState("small");
  const [setDefaultSourceLang, setSetDefaultSourceLang] = useState("");
  const [setDefaultLang, setSetDefaultLang] = useState("");
  const [setForceCpu, setSetForceCpu] = useState(false);
  const [setPort, setSetPort] = useState(8000);
  const [settingsStatus, setSettingsStatus] = useState("");
  const [loadedModels, setLoadedModels] = useState({ whisper_models: [], diarization_loaded: false });
  const [unloadStatus, setUnloadStatus] = useState("");

  // --- Initial load: check auth, then models + settings ---
  useEffect(() => {
    (async () => {
      try {
        const res = await fetch("/api/auth/status");
        const s = await res.json();
        if (s.auth_required && !s.authenticated) {
          router.push("/login");
          return;
        }
      } catch {
        // If the status check itself fails, fall through and let the first
        // protected API call surface the problem.
      }
      setAuthChecked(true);

      try {
        const res = await apiFetch("/api/models");
        const { models: list } = await res.json();
        setModels(list);
      } catch {
        setModels(["small"]);
      }

      try {
        const res = await apiFetch("/api/settings");
        if (res.ok) {
          const s = await res.json();
          setHfTokenSet(!!s.hf_token_set);
          setAppPasswordSet(!!s.app_password_set);
          if (s.default_model) {
            setModelSize(s.default_model);
            setSetDefaultModel(s.default_model);
          }
          setTargetLang(s.default_lang || "");
          setSetDefaultLang(s.default_lang || "");
          setSourceLang(s.default_source_lang || "");
          setSetDefaultSourceLang(s.default_source_lang || "");
          setSetForceCpu(!!s.force_cpu);
          setSetPort(s.port || 8000);
        }
      } catch {
        // Settings are optional; ignore failures here.
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // --- Close the settings modal on Escape ---
  useEffect(() => {
    if (!settingsOpen) return undefined;
    const onKey = (e) => { if (e.key === "Escape") setSettingsOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [settingsOpen]);

  async function refreshLoadedModels() {
    try {
      const res = await apiFetch("/api/models/loaded");
      if (res.ok) setLoadedModels(await res.json());
    } catch {
      // Non-fatal: the unload button just won't have fresh info until retried.
    }
  }

  // --- Refresh loaded-model info whenever Settings is opened ---
  useEffect(() => {
    if (settingsOpen) {
      setUnloadStatus("");
      refreshLoadedModels();
    }
  }, [settingsOpen]);

  async function handleUnloadModels() {
    setUnloadStatus("Unloading...");
    try {
      const res = await apiFetch("/api/models/unload", { method: "POST" });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Unload failed (${res.status})`);
      }
      setUnloadStatus("Models unloaded - memory freed.");
      await refreshLoadedModels();
    } catch (err) {
      setUnloadStatus(err.message);
    }
  }

  // --- Job polling ---
  useEffect(() => {
    if (!currentJobId) return undefined;

    pollTimerRef.current = setInterval(async () => {
      try {
        const res = await apiFetch(`/api/jobs/${currentJobId}`);
        if (!res.ok) throw new Error(`Status check failed (${res.status})`);
        const job = await res.json();

        const pct = job.percent || 0;
        const label = STATUS_LABELS[job.status] || job.status;
        setProgressStatus(label);
        setProgressPercent(pct);
        setProgressEta(formatEta(job.eta_seconds));
        setJobStatus(job.status);

        if (job.status === "done") {
          clearInterval(pollTimerRef.current);
          setProgressPercent(100);
          setJobDone(true);
          setDownloadReady(true);
          setFormDisabled(false);
          setResultSubtitleMode(job.subtitle_mode || "hardsub");
          try {
            const tRes = await apiFetch(`/api/jobs/${currentJobId}/transcript`);
            if (tRes.ok) setTranscript(await tRes.text());
          } catch {
            // Non-fatal: the download link still works even if the inline preview fails.
          }
          if (job.speakers && job.speakers.length) {
            setSpeakers(job.speakers);
            const initial = {};
            for (const s of job.speakers) {
              const custom = job.speaker_names?.[s];
              initial[s] = custom && custom !== s ? custom : "";
            }
            setSpeakerInputs(initial);
          }
        } else if (job.status === "error") {
          clearInterval(pollTimerRef.current);
          setErrorMessage(job.error || "Processing failed.");
          setFormDisabled(false);
        } else if (job.status === "cancelled") {
          clearInterval(pollTimerRef.current);
          setFormDisabled(false);
        }
      } catch (err) {
        clearInterval(pollTimerRef.current);
        setErrorMessage(err.message);
        setFormDisabled(false);
      }
    }, 2000);

    return () => clearInterval(pollTimerRef.current);
  }, [currentJobId]);

  function setFile(file) {
    setSelectedFile(file);
  }

  function resetOutcome() {
    setDownloadReady(false);
    setJobDone(false);
    setJobStatus("");
    setTranscript(null);
    setSpeakers([]);
    setSpeakerInputs({});
    setErrorMessage("");
  }

  async function handleCancelJob() {
    if (!currentJobId) return;
    setJobStatus("cancelling");
    setProgressStatus(STATUS_LABELS.cancelling);
    try {
      const res = await apiFetch(`/api/jobs/${currentJobId}/cancel`, { method: "POST" });
      if (!res.ok && res.status !== 409) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Cancel failed (${res.status})`);
      }
    } catch (err) {
      setErrorMessage(err.message);
    }
  }

  async function handleSubmit() {
    if (!selectedFile) return;
    resetOutcome();
    setFormDisabled(true);
    setProgressVisible(true);
    setProgressStatus("Uploading...");
    setProgressPercent(0);
    setProgressEta("");

    const form = new FormData();
    form.append("video", selectedFile);
    form.append("model_size", modelSize);
    form.append("source_lang", sourceLang);
    form.append("target_lang", targetLang);
    form.append("diarize", diarize ? "true" : "false");
    form.append("subtitle_mode", subtitleMode);

    try {
      const res = await apiFetch("/api/jobs", { method: "POST", body: form });
      if (!res.ok) throw new Error(`Upload failed (${res.status})`);
      const { job_id } = await res.json();
      setCurrentJobId(job_id);
    } catch (err) {
      setErrorMessage(err.message);
      setFormDisabled(false);
    }
  }

  async function handleSaveSettings() {
    setSettingsStatus("Saving...");
    const body = {
      default_model: setDefaultModel,
      default_lang: setDefaultLang,
      default_source_lang: setDefaultSourceLang,
      force_cpu: setForceCpu,
      port: parseInt(setPort, 10) || 8000,
    };
    if (setHfToken.trim()) body.hf_token = setHfToken.trim();
    if (setAppPassword.trim()) body.app_password = setAppPassword.trim();

    try {
      const res = await apiFetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(`Save failed (${res.status})`);
      const s = await res.json();
      setSetHfToken("");
      setHfTokenSet(!!s.hf_token_set);
      const passwordWasJustSet = !appPasswordSet && !!s.app_password_set;
      setAppPasswordSet(!!s.app_password_set);
      setSetAppPassword("");
      setModelSize(s.default_model);
      setTargetLang(s.default_lang || "");
      setSourceLang(s.default_source_lang || "");
      setSettingsStatus(passwordWasJustSet ? "Saved. Log in with the new password next time." : "Saved.");
    } catch (err) {
      setSettingsStatus(err.message);
    }
    setTimeout(() => setSettingsStatus(""), 4000);
  }

  async function handleLogout() {
    await fetch("/api/auth/logout", { method: "POST" });
    router.push("/login");
  }

  async function handleApplySpeakerNames() {
    if (!currentJobId) return;
    const names = {};
    for (const [speaker, name] of Object.entries(speakerInputs)) {
      if (name.trim()) names[speaker] = name.trim();
    }
    try {
      const res = await apiFetch(`/api/jobs/${currentJobId}/speakers`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ names }),
      });
      if (!res.ok) throw new Error(`Renaming speakers failed (${res.status})`);
      const data = await res.json();
      setTranscript(data.transcript);
    } catch (err) {
      setErrorMessage(err.message);
    }
  }

  function copyTranscript() {
    if (transcript) navigator.clipboard?.writeText(transcript);
  }

  if (!authChecked) return null;

  return (
    <div className="page">
      <div className="card">
        <div className="header-row">
          <div className="brand">
            <div className="brand-mark"><MicIcon size={22} /></div>
            <div>
              <h1>Subtitle Burner</h1>
              <p className="subtitle">Upload a video, get one back with subtitles burned in - plus a full transcript.</p>
            </div>
          </div>
          <button
            className={`icon-btn ${settingsOpen ? "active" : ""}`}
            title="Settings"
            onClick={() => setSettingsOpen((v) => !v)}
          >
            <SettingsIcon />
          </button>
        </div>

        {settingsOpen && (
          <div className="modal-overlay" onClick={() => setSettingsOpen(false)}>
            <div className="modal-panel" onClick={(e) => e.stopPropagation()}>
              <div className="modal-head">
                <div>
                  <h2>Settings</h2>
                  <p>Saved locally and reused as defaults for new jobs.</p>
                </div>
                <button className="icon-btn" title="Close" onClick={() => setSettingsOpen(false)}>
                  <XIcon size={16} />
                </button>
              </div>

              <div className="modal-body">
                <div className="settings-section">
                  <div className="settings-section-title">Access</div>
                  <div className="settings-field">
                    <label htmlFor="setHfToken">Hugging Face access token</label>
                    <input type="password" id="setHfToken" placeholder="For speaker separation" value={setHfToken} onChange={(e) => setSetHfToken(e.target.value)} />
                    <div className="hint">
                      {hfTokenSet
                        ? "A token is currently saved. Leave blank to keep it, or enter a new one to replace it."
                        : "No token saved yet. Required for speaker separation."}
                    </div>
                  </div>
                  <div className="settings-field">
                    <label htmlFor="setAppPassword">App password</label>
                    <input type="password" id="setAppPassword" placeholder="Protects this site once reachable off this PC" value={setAppPassword} onChange={(e) => setSetAppPassword(e.target.value)} />
                    <div className="hint">
                      {appPasswordSet
                        ? "A password is currently set. Leave blank to keep it, enter a new one to replace it, or save empty to remove it."
                        : "No password set - anyone who can reach this site can use it."}
                    </div>
                  </div>
                </div>

                <div className="settings-section">
                  <div className="settings-section-title">Defaults for new jobs</div>
                  <div className="settings-field">
                    <label htmlFor="setDefaultModel">Default Whisper model</label>
                    <select id="setDefaultModel" value={setDefaultModel} onChange={(e) => setSetDefaultModel(e.target.value)}>
                      {models.map((m) => (
                        <option key={m} value={m}>{MODEL_HINTS[m] ? `${m} — ${MODEL_HINTS[m]}` : m}</option>
                      ))}
                    </select>
                  </div>
                  <div className="grid-2">
                    <div className="settings-field">
                      <label htmlFor="setDefaultSourceLang">Spoken language</label>
                      <LangSelect id="setDefaultSourceLang" value={setDefaultSourceLang} onChange={(e) => setSetDefaultSourceLang(e.target.value)} placeholder="Auto-detect" />
                    </div>
                    <div className="settings-field">
                      <label htmlFor="setDefaultLang">Subtitle language</label>
                      <LangSelect id="setDefaultLang" value={setDefaultLang} onChange={(e) => setSetDefaultLang(e.target.value)} placeholder="No translation" />
                    </div>
                  </div>
                  <div className="toggle-row" style={{ marginTop: 14 }}>
                    <div className="toggle-text">
                      <div className="toggle-title">Force CPU-only</div>
                      <div className="hint">Skip GPU/CUDA - useful if GPU transcription ever misbehaves.</div>
                    </div>
                    <Switch checked={setForceCpu} onChange={(e) => setSetForceCpu(e.target.checked)} />
                  </div>
                </div>

                <div className="settings-section">
                  <div className="settings-section-title">Server</div>
                  <div className="settings-field">
                    <label htmlFor="setPort">Port</label>
                    <input type="number" id="setPort" min="1" max="65535" value={setPort} onChange={(e) => setSetPort(e.target.value)} />
                    <div className="hint">Requires restarting the app to take effect.</div>
                  </div>
                </div>

                <div className="settings-section">
                  <div className="settings-section-title"><CpuIcon size={14} /> Memory</div>
                  {loadedModels.whisper_models.length === 0 && !loadedModels.diarization_loaded ? (
                    <div className="hint">No models currently loaded in memory.</div>
                  ) : (
                    <ul className="loaded-model-list">
                      {loadedModels.whisper_models.map((m) => (
                        <li key={m.model_size}>Whisper <strong>{m.model_size}</strong> — {m.device}</li>
                      ))}
                      {loadedModels.diarization_loaded && <li>Speaker-diarization pipeline</li>}
                    </ul>
                  )}
                  <div className="hint" style={{ marginTop: 8 }}>
                    Loaded models stay resident (GPU/RAM) between jobs so the next one starts faster. Unload them to free that memory for other apps - they reload automatically next time they&apos;re needed.
                  </div>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    style={{ marginTop: 10 }}
                    disabled={loadedModels.whisper_models.length === 0 && !loadedModels.diarization_loaded}
                    onClick={handleUnloadModels}
                  >
                    <EjectIcon size={15} /> Unload models
                  </button>
                  {unloadStatus && <div className="hint" style={{ marginTop: 6 }}>{unloadStatus}</div>}
                </div>
              </div>

              <div className="modal-foot">
                <div className="modal-foot-actions">
                  <button className="btn btn-primary" style={{ margin: 0, width: "auto" }} onClick={handleSaveSettings}>Save settings</button>
                  {appPasswordSet && (
                    <button type="button" className="btn btn-secondary" onClick={handleLogout}>
                      <LogOutIcon size={15} /> Log out
                    </button>
                  )}
                </div>
                <span className="settings-status">{settingsStatus}</span>
              </div>
            </div>
          </div>
        )}

        <div
          className={`dropzone ${dragover ? "dragover" : ""}`}
          onClick={() => fileInputRef.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setDragover(true); }}
          onDragLeave={() => setDragover(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragover(false);
            if (e.dataTransfer.files.length) setFile(e.dataTransfer.files[0]);
          }}
        >
          <div className="dz-icon"><UploadCloudIcon size={30} /></div>
          <div className="dz-text">Drag &amp; drop a video here, or <strong>click to choose a file</strong></div>
          {selectedFile && (
            <div className="file-chip" onClick={(e) => e.stopPropagation()}>
              <span className="name">{selectedFile.name}</span>
              <span style={{ color: "var(--faint)" }}>{formatBytes(selectedFile.size)}</span>
              <button onClick={() => setSelectedFile(null)} title="Remove"><XIcon size={13} /></button>
            </div>
          )}
        </div>
        <input
          type="file"
          accept="video/*"
          ref={fileInputRef}
          style={{ display: "none" }}
          onChange={(e) => { if (e.target.files.length) setFile(e.target.files[0]); }}
        />

        <div className="section">
          <div className="section-label">Whisper model (accuracy vs. speed)</div>
          <select value={modelSize} onChange={(e) => setModelSize(e.target.value)} disabled={formDisabled}>
            {models.map((m) => (
              <option key={m} value={m}>{MODEL_HINTS[m] ? `${m} — ${MODEL_HINTS[m]}` : m}</option>
            ))}
          </select>
        </div>

        <div className="section grid-2">
          <div>
            <div className="section-label">Spoken language</div>
            <LangSelect value={sourceLang} onChange={(e) => setSourceLang(e.target.value)} placeholder="Auto-detect" disabled={formDisabled} />
          </div>
          <div>
            <div className="section-label">Subtitle language</div>
            <LangSelect value={targetLang} onChange={(e) => setTargetLang(e.target.value)} placeholder="No translation" disabled={formDisabled} />
          </div>
        </div>
        <div className="hint" style={{ marginTop: 8 }}>
          Auto-detect works for most videos, but can misfire (or even translate to English on its own) for some languages. If you know the video is Persian, select it above to force accurate results.
        </div>

        <div className="toggle-row">
          <div className="toggle-text">
            <div className="toggle-title"><UsersIcon size={15} /> Separate speakers</div>
            <div className="hint">Labels each part of the transcript &quot;Speaker 1:&quot;, &quot;Speaker 2:&quot;, etc. - great for podcasts/interviews. Renameable afterwards.</div>
          </div>
          <Switch checked={diarize} onChange={(e) => setDiarize(e.target.checked)} disabled={formDisabled} />
        </div>

        <div className="section">
          <div className="section-label">Subtitle delivery</div>
          <div className="segmented">
            <button
              type="button"
              className={`segmented-option ${subtitleMode === "hardsub" ? "active" : ""}`}
              disabled={formDisabled}
              onClick={() => setSubtitleMode("hardsub")}
            >
              Hardsub (burned in)
            </button>
            <button
              type="button"
              className={`segmented-option ${subtitleMode === "softsub" ? "active" : ""}`}
              disabled={formDisabled}
              onClick={() => setSubtitleMode("softsub")}
            >
              Softsub (selectable track)
            </button>
          </div>
          <div className="hint" style={{ marginTop: 8 }}>
            {subtitleMode === "hardsub"
              ? "Subtitles are permanently drawn into the video image. Always visible, works in every player and app - including on iPhone."
              : "Subtitles are embedded as a separate .mkv track you can toggle on/off. Original video is copied untouched (fast, no quality loss), but not all players show soft subtitles automatically - check your player supports it."}
          </div>
        </div>

        <button className="btn btn-primary" disabled={!selectedFile || formDisabled} onClick={handleSubmit}>
          <UploadCloudIcon size={17} /> Upload &amp; Process
        </button>

        {progressVisible && (
          <div className="progress-wrap">
            <div className="progress-head">
              <div className="progress-label">
                {!jobDone && <LoaderIcon size={15} className="spin" />}
                {jobDone && <CheckCircleIcon size={15} style={{ color: "var(--success)" }} />}
                {progressStatus}{progressEta && !jobDone ? ` — ${progressEta}` : ""}
              </div>
              <div className="progress-pct">{progressPercent}%</div>
            </div>
            <div className="bar-track">
              <div className={`bar-fill ${jobDone ? "done" : ""}`} style={{ width: `${progressPercent}%` }} />
            </div>
            {!jobDone && jobStatus !== "cancelling" && jobStatus !== "cancelled" && (
              <button type="button" className="btn btn-ghost btn-sm" style={{ marginTop: 10 }} onClick={handleCancelJob}>
                <XIcon size={14} /> Cancel
              </button>
            )}
          </div>
        )}

        {downloadReady && (
          <div className="result-block">
            <div className="done-banner"><CheckCircleIcon size={18} /> Your video is ready</div>
            <div className="download-row">
              <a className="primary" href={`/api/jobs/${currentJobId}/download`} download>
                <DownloadIcon size={16} /> Download video{resultSubtitleMode === "softsub" ? " (.mkv, softsub)" : " (hardsub)"}
              </a>
              <a href={`/api/jobs/${currentJobId}/transcript`} download>
                <DownloadIcon size={16} /> Download transcript
              </a>
            </div>

            {speakers.length > 0 && (
              <div className="speaker-block">
                <h3><UsersIcon size={15} /> Rename speakers</h3>
                {speakers.map((s) => (
                  <div className="speaker-row" key={s}>
                    <span className="speaker-pill">{s}</span>
                    <input
                      type="text"
                      placeholder={`Real name for ${s}`}
                      value={speakerInputs[s] || ""}
                      onChange={(e) => setSpeakerInputs((prev) => ({ ...prev, [s]: e.target.value }))}
                    />
                  </div>
                ))}
                <button className="btn btn-secondary btn-sm" style={{ marginTop: 4 }} onClick={handleApplySpeakerNames}>Apply names</button>
              </div>
            )}

            {transcript != null && (
              <div className="transcript-block">
                <div className="transcript-head">
                  <div className="section-label">Transcript preview</div>
                  <button className="btn btn-ghost btn-sm" onClick={copyTranscript} title="Copy to clipboard">Copy</button>
                </div>
                <div className="transcript-box">{transcript}</div>
              </div>
            )}
          </div>
        )}

        {errorMessage && (
          <div className="error-banner">
            <AlertTriangleIcon size={17} />
            <span>{errorMessage}</span>
          </div>
        )}
      </div>

      <div className="log-toggle-wrap">
        <button className="log-toggle" onClick={() => setLogsOpen((v) => !v)}>
          <TerminalIcon size={14} />
          {logsOpen ? "Hide backend log" : "Show backend log"}
          <ChevronDownIcon size={14} style={{ transform: logsOpen ? "rotate(180deg)" : "none", transition: "transform 0.15s ease" }} />
        </button>
      </div>
      {logsOpen && <LogConsole />}

      <div className="footer-note">Subtitle Burner - running locally on your network</div>
    </div>
  );
}
