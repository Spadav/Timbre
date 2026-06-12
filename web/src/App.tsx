import {
  ClipboardList,
  Cpu,
  Headphones,
  Mic,
  Play,
  Radio,
  RefreshCw,
  Settings,
  Sparkles,
  Square,
  Terminal,
  Trash2,
  Upload,
  Volume2
} from "lucide-react";
import { ChangeEvent, FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

type Page = "speak" | "listen" | "qwen" | "backends" | "models" | "voices" | "log" | "config" | "api";

type Backend = {
  name: string;
  kind: "tts" | "stt";
  enabled: boolean;
  loaded: boolean;
  ttl: number;
  device: string;
};

type Voice = {
  name: string;
  backend?: string;
  type: "preset" | "cloned" | "alias";
  target?: string;
  audio_path?: string | null;
  prepared_backends?: string[];
};

type QwenCloneVoice = {
  name: string;
  type: "clone";
  audio_path?: string | null;
  ref_text?: string | null;
  design?: string | null;
  prepared: boolean;
};

type QwenPresetVoice = {
  name: string;
  type: "preset";
};

type QwenVoices = {
  clones: QwenCloneVoice[];
  presets: QwenPresetVoice[];
};

type QwenModelSize = "0.6b" | "1.7b";

type ModelRecord = {
  id: string;
  object: "model";
  kind: "tts" | "stt";
  backend: string;
  label: string;
  path: string;
  downloadable: boolean;
  installed: boolean;
  active: boolean;
};

type Health = {
  status: string;
  service: string;
};

type ActivityEntry = {
  id: string;
  time: string;
  type: "TTS" | "STT";
  backend: string;
  input: string;
  duration: number;
  format: string;
  status: "ok" | "error";
};

type BackendSettings = {
  enabled: boolean;
  device: string;
  ttl: number;
  [key: string]: unknown;
};

type ConfigGroup = {
  default: string;
  backends: Record<string, BackendSettings>;
};

type AppConfig = {
  server: {
    host: string;
    port: number;
    ttl_check_interval: number;
  };
  tts: ConfigGroup;
  stt: ConfigGroup;
  voices: {
    dir: string;
    aliases: Record<string, Record<string, string>>;
  };
};

type ConfigResponse = {
  path: string;
  config: AppConfig;
};

const api = {
  async health(): Promise<Health> {
    const res = await fetch("/health");
    if (!res.ok) throw new Error("health check failed");
    return res.json();
  },
  async backends(): Promise<Backend[]> {
    const res = await fetch("/v1/backends");
    if (!res.ok) throw new Error("backend list failed");
    const body = await res.json();
    return body.data;
  },
  async voices(): Promise<Voice[]> {
    const res = await fetch("/v1/voices");
    if (!res.ok) throw new Error("voice list failed");
    const body = await res.json();
    return body.data;
  },
  async models(): Promise<ModelRecord[]> {
    const res = await fetch("/v1/models");
    if (!res.ok) throw new Error("model list failed");
    const body = await res.json();
    return body.data;
  },
  async config(): Promise<ConfigResponse> {
    const res = await fetch("/v1/config");
    if (!res.ok) throw new Error("config load failed");
    return res.json();
  },
  async saveConfig(config: AppConfig): Promise<ConfigResponse> {
    const res = await fetch("/v1/config", {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(config)
    });
    if (!res.ok) {
      const body = await safeJson(res);
      throw new Error(body.detail || "config save failed");
    }
    return res.json();
  },
  async setVoiceAlias(backend: string, alias: string, target: string): Promise<Voice[]> {
    const res = await fetch("/v1/voices/aliases", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ backend, alias, target })
    });
    if (!res.ok) {
      const body = await safeJson(res);
      throw new Error(body.detail || "voice alias save failed");
    }
    const body = await res.json();
    return body.data;
  },
  async deleteVoiceAlias(backend: string, alias: string): Promise<Voice[]> {
    const res = await fetch(`/v1/voices/aliases/${encodeURIComponent(backend)}/${encodeURIComponent(alias)}`, {
      method: "DELETE"
    });
    if (!res.ok) {
      const body = await safeJson(res);
      throw new Error(body.detail || "voice alias delete failed");
    }
    const body = await res.json();
    return body.data;
  },
  async prepareVoice(name: string, backend: string): Promise<unknown> {
    const form = new FormData();
    form.append("backend", backend);
    const res = await fetch(`/v1/voices/${encodeURIComponent(name)}/prepare`, {
      method: "POST",
      body: form
    });
    if (!res.ok) {
      const body = await safeJson(res);
      throw new Error(body.detail || `voice prepare failed: ${res.status}`);
    }
    return res.json();
  },
  async backendAction(kind: Backend["kind"], name: string, action: "load" | "unload" | "enable" | "disable"): Promise<Backend[]> {
    const res = await fetch(`/v1/backends/${kind}/${encodeURIComponent(name)}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ action })
    });
    if (!res.ok) {
      const body = await safeJson(res);
      throw new Error(body.detail || `backend ${action} failed`);
    }
    const body = await res.json();
    return body.data;
  },
  async modelAction(id: string, action: "download" | "set_active"): Promise<ModelRecord[]> {
    const res = await fetch(`/v1/models/${encodeURIComponent(id)}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ action })
    });
    if (!res.ok) {
      const body = await safeJson(res);
      throw new Error(body.detail || `model ${action} failed`);
    }
    const body = await res.json();
    return body.data;
  },
  async qwenVoices(): Promise<QwenVoices> {
    const res = await fetch("/v1/qwen/voices");
    if (!res.ok) throw new Error("qwen voice list failed");
    const body = await res.json();
    return body.data;
  }
};

const QWEN_LANGUAGES = [
  "Auto",
  "English",
  "Chinese",
  "Japanese",
  "Korean",
  "German",
  "French",
  "Russian",
  "Portuguese",
  "Spanish",
  "Italian"
];

function App() {
  const [page, setPage] = useState<Page>("speak");
  const [online, setOnline] = useState(false);
  const [backends, setBackends] = useState<Backend[]>([]);
  const [models, setModels] = useState<ModelRecord[]>([]);
  const [voices, setVoices] = useState<Voice[]>([]);
  const [statusText, setStatusText] = useState("starting");
  const [activity, setActivity] = useState<ActivityEntry[]>([]);

  const addActivity = useCallback((entry: Omit<ActivityEntry, "id" | "time">) => {
    setActivity((current) => [
      {
        ...entry,
        id: makeId(),
        time: new Date().toLocaleTimeString([], { hour12: false })
      },
      ...current
    ].slice(0, 80));
  }, []);

  const refresh = useCallback(async () => {
    try {
      const [health, backendList, modelList, voiceList] = await Promise.all([
        api.health(),
        api.backends(),
        api.models(),
        api.voices()
      ]);
      setOnline(health.status === "ok");
      setBackends(backendList);
      setModels(modelList);
      setVoices(voiceList);
      setStatusText("online");
    } catch (err) {
      setOnline(false);
      setStatusText(err instanceof Error ? err.message : "offline");
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = window.setInterval(refresh, 3000);
    return () => window.clearInterval(id);
  }, [refresh]);

  const loadedCount = backends.filter((backend) => backend.loaded).length;

  return (
    <div className="app-shell">
      <aside className="side">
        <div className="logo">
          <div className="logo-name">
            <span>T</span>imbre
          </div>
          <div className="logo-sub">local voice gateway</div>
        </div>
        <nav className="nav">
          <NavItem page="speak" active={page} onClick={setPage} label="Speak" icon={<Volume2 />} />
          <NavItem page="listen" active={page} onClick={setPage} label="Listen" icon={<Headphones />} />
          <NavItem page="qwen" active={page} onClick={setPage} label="Qwen Studio" icon={<Sparkles />} />
          <NavItem page="backends" active={page} onClick={setPage} label="Backends" icon={<Radio />} />
          <NavItem page="models" active={page} onClick={setPage} label="Models" icon={<Cpu />} />
          <NavItem page="voices" active={page} onClick={setPage} label="Voices" icon={<Mic />} />
          <NavItem page="log" active={page} onClick={setPage} label="Log" icon={<ClipboardList />} />
          <NavItem page="config" active={page} onClick={setPage} label="Config" icon={<Settings />} />
          <NavItem page="api" active={page} onClick={setPage} label="API" icon={<Terminal />} />
        </nav>
        <div className="side-status">
          <div className="side-status-row">
            <span className={online ? "dot-g" : "dot-r"} />
            {statusText}
          </div>
          <div className="side-status-row">Port 9000</div>
          <div className="side-status-row">
            Backends: {loadedCount}/{backends.length || 0}
          </div>
        </div>
      </aside>
      <main className="main">
        <header className="header">
          <div className="header-left">{pageLabel(page)}</div>
          <div className="header-right">
            <button className="icon-btn" onClick={refresh} title="Refresh">
              <RefreshCw size={14} />
            </button>
            <div className={online ? "badge badge-on" : "badge badge-off"}>
              <span className={online ? "dot-g" : "dot-r"} />
              {online ? "online" : "offline"}
            </div>
            <div className="badge">v0.1.0</div>
          </div>
        </header>
        <section className="content">
          {page === "speak" && (
            <SpeakPage
              backends={backends}
              voices={voices}
              activity={activity}
              onActivity={addActivity}
              onRefresh={refresh}
            />
          )}
          {page === "listen" && <ListenPage backends={backends} onActivity={addActivity} />}
          {page === "qwen" && (
            <QwenStudioPage
              backends={backends}
              models={models}
              onActivity={addActivity}
              onRefresh={refresh}
            />
          )}
          {page === "backends" && <BackendsPage backends={backends} onRefresh={refresh} />}
          {page === "models" && <ModelsPage models={models} onRefresh={refresh} />}
          {page === "voices" && <VoicesPage voices={voices} onRefresh={refresh} />}
          {page === "log" && <LogPage activity={activity} />}
          {page === "config" && <ConfigPage backends={backends} onRefresh={refresh} />}
          {page === "api" && <ApiPage backends={backends} voices={voices} />}
        </section>
      </main>
    </div>
  );
}

function NavItem({
  page,
  active,
  label,
  icon,
  onClick
}: {
  page: Page;
  active: Page;
  label: string;
  icon: React.ReactNode;
  onClick: (page: Page) => void;
}) {
  return (
    <button className={`nav-item ${active === page ? "active" : ""}`} onClick={() => onClick(page)}>
      <span className="nav-dot" />
      <span className="nav-icon">{icon}</span>
      {label}
    </button>
  );
}

function SpeakPage({
  backends,
  voices,
  activity,
  onActivity,
  onRefresh
}: {
  backends: Backend[];
  voices: Voice[];
  activity: ActivityEntry[];
  onActivity: (entry: Omit<ActivityEntry, "id" | "time">) => void;
  onRefresh: () => void;
}) {
  const ttsBackends = backends.filter((backend) => backend.kind === "tts" && backend.enabled);
  const [text, setText] = useState("Hello, this is Timbre speaking through a local voice gateway.");
  const [backend, setBackend] = useState("pocket");
  const [voice, setVoice] = useState("default");
  const [format, setFormat] = useState("wav");
  const [speed, setSpeed] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [audioUrl, setAudioUrl] = useState("");
  const [duration, setDuration] = useState(0);
  const [generationSeconds, setGenerationSeconds] = useState(0);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioPlayer = useAudioPlayer(audioRef, audioUrl);
  const waveformRef = useWaveform(audioUrl);
  const sphereEnergyRef = useAudioEnergy(audioRef, audioUrl, busy);

  const voiceOptions = useMemo(() => {
    const cloned = voices.filter(
      (item) => item.type === "cloned" && item.prepared_backends?.includes(backend)
    );
    const presets = voices.filter(
      (item) => (item.type === "preset" || item.type === "alias") && item.backend === backend
    );
    return [...cloned, ...presets].map((item) => item.name);
  }, [backend, voices]);

  useEffect(() => {
    if (ttsBackends.length && !ttsBackends.some((item) => item.name === backend)) {
      setBackend(ttsBackends[0].name);
    }
  }, [backend, ttsBackends]);

  useEffect(() => {
    if (voiceOptions.length && !voiceOptions.includes(voice)) {
      setVoice(voiceOptions[0]);
    }
  }, [voice, voiceOptions]);

  async function generate() {
    setBusy(true);
    setError("");
    const start = performance.now();
    try {
      const res = await fetch("/v1/audio/speech", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          model: backend,
          input: text,
          voice,
          response_format: format,
          speed
        })
      });
      if (!res.ok) {
        const body = await safeJson(res);
        throw new Error(body.detail || `speech failed: ${res.status}`);
      }
      const blob = await res.blob();
      if (audioUrl) URL.revokeObjectURL(audioUrl);
      setAudioUrl(URL.createObjectURL(blob));
      const elapsed = (performance.now() - start) / 1000;
      setGenerationSeconds(elapsed);
      onActivity({
        type: "TTS",
        backend,
        input: text,
        duration: elapsed,
        format,
        status: "ok"
      });
      onRefresh();
    } catch (err) {
      onActivity({
        type: "TTS",
        backend,
        input: text,
        duration: (performance.now() - start) / 1000,
        format,
        status: "error"
      });
      setError(err instanceof Error ? err.message : "generation failed");
    } finally {
      setBusy(false);
    }
  }

  const rtf = duration > 0 && generationSeconds > 0 ? generationSeconds / duration : 0;

  return (
    <div className="speak-layout">
      <div className="page-grid speak-main">
        <SectionHeader num="01" title="input" right={`${text.length}/4096`} />
        <textarea
          className="input-area text-input"
          maxLength={4096}
          value={text}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={(event) => {
            if ((event.ctrlKey || event.metaKey) && event.key === "Enter") generate();
          }}
        />
        <div className="input-meta">
          <div className="input-meta-left">31 languages · wav / mp3 / opus / flac</div>
        </div>

        <SectionHeader num="02" title="parameters" />
        <div className="params">
          <SelectParam label="backend" value={backend} values={ttsBackends.map((item) => item.name)} onChange={setBackend} accent />
          <SelectParam label="voice" value={voice} values={voiceOptions} onChange={setVoice} />
          <SelectParam label="format" value={format} values={["wav", "mp3", "opus", "ogg", "flac"]} onChange={setFormat} />
          <div className="param">
            <div className="param-label">speed</div>
            <div className="slider-row">
              <input className="range" type="range" min="0.5" max="1.5" step="0.05" value={speed} onChange={(event) => setSpeed(Number(event.target.value))} />
              <div className="slider-val">{speed.toFixed(2)}</div>
            </div>
          </div>
        </div>

        <SectionHeader num="03" title="output" right={duration ? `${duration.toFixed(1)}s` : "0.0s"} />
        <div className="wave-area">
          <div className="wave-player">
            <button className="play-btn" onClick={audioPlayer.toggle} disabled={!audioUrl} title={audioPlayer.playing ? "Stop" : "Play"}>
              {audioPlayer.playing ? <Square size={15} /> : <Play size={15} />}
            </button>
            <div className="track" />
            <div className="wave-time">
              {formatTime(audioPlayer.currentTime)} / {formatTime(duration)}
            </div>
          </div>
          <canvas className="wave-canvas" ref={waveformRef} />
          <audio ref={audioRef} src={audioUrl} onLoadedMetadata={(event) => setDuration(event.currentTarget.duration || 0)} />
        </div>

        <div className="metrics-row">
          <Metric label="generation" value={generationSeconds ? `${generationSeconds.toFixed(2)}s` : "-"} />
          <Metric label="audio" value={duration ? `${duration.toFixed(2)}s` : "-"} />
          <Metric label="rtf" value={rtf ? `${rtf.toFixed(2)}x` : "-"} />
        </div>

        {error && <div className="error-line">{error}</div>}
        <button className="gen-bar" onClick={generate} disabled={busy || !text.trim()}>
          <span className="gen-text">{busy ? "Generating_" : "Generate_"}</span>
          <span className="gen-hint">ctrl+enter</span>
        </button>
      </div>
      <aside className="speak-rail">
        <WireframeSphere energyRef={sphereEnergyRef} />
        <CompactActivityLog activity={activity} />
      </aside>
    </div>
  );
}

function ListenPage({
  backends,
  onActivity
}: {
  backends: Backend[];
  onActivity: (entry: Omit<ActivityEntry, "id" | "time">) => void;
}) {
  const sttBackends = backends.filter((backend) => backend.kind === "stt" && backend.enabled);
  const [backend, setBackend] = useState("parakeet");
  const [file, setFile] = useState<File | null>(null);
  const [recording, setRecording] = useState(false);
  const [mediaRecorder, setMediaRecorder] = useState<MediaRecorder | null>(null);
  const [audioUrl, setAudioUrl] = useState("");
  const [duration, setDuration] = useState(0);
  const [transcript, setTranscript] = useState("");
  const [processingSeconds, setProcessingSeconds] = useState(0);
  const [error, setError] = useState("");
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioPlayer = useAudioPlayer(audioRef, audioUrl);
  const waveformRef = useWaveform(audioUrl);

  useEffect(() => {
    if (sttBackends.length && !sttBackends.some((item) => item.name === backend)) {
      setBackend(sttBackends[0].name);
    }
  }, [backend, sttBackends]);

  function pickFile(event: ChangeEvent<HTMLInputElement>) {
    const next = event.target.files?.[0] || null;
    setFile(next);
    setTranscript("");
    if (audioUrl) URL.revokeObjectURL(audioUrl);
    setAudioUrl(next ? URL.createObjectURL(next) : "");
  }

  async function toggleRecording() {
    if (recording && mediaRecorder) {
      mediaRecorder.stop();
      return;
    }
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const chunks: Blob[] = [];
    const recorder = new MediaRecorder(stream);
    recorder.ondataavailable = (event) => chunks.push(event.data);
    recorder.onstop = () => {
      stream.getTracks().forEach((track) => track.stop());
      const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
      const recordedFile = new File([blob], "recording.webm", { type: blob.type });
      setFile(recordedFile);
      if (audioUrl) URL.revokeObjectURL(audioUrl);
      setAudioUrl(URL.createObjectURL(blob));
      setRecording(false);
      setMediaRecorder(null);
    };
    recorder.start();
    setMediaRecorder(recorder);
    setRecording(true);
  }

  async function transcribe() {
    if (!file) return;
    setError("");
    const form = new FormData();
    form.append("model", backend);
    form.append("file", file);
    const start = performance.now();
    try {
      const res = await fetch("/v1/audio/transcriptions", { method: "POST", body: form });
      if (!res.ok) {
        const body = await safeJson(res);
        throw new Error(body.detail || `transcription failed: ${res.status}`);
      }
      const body = await res.json();
      setTranscript(body.text || "");
      const elapsed = (performance.now() - start) / 1000;
      setProcessingSeconds(elapsed);
      onActivity({
        type: "STT",
        backend,
        input: file.name,
        duration: elapsed,
        format: file.name.split(".").pop() || "audio",
        status: "ok"
      });
    } catch (err) {
      onActivity({
        type: "STT",
        backend,
        input: file.name,
        duration: (performance.now() - start) / 1000,
        format: file.name.split(".").pop() || "audio",
        status: "error"
      });
      setError(err instanceof Error ? err.message : "transcription failed");
    }
  }

  const rtf = duration > 0 && processingSeconds > 0 ? processingSeconds / duration : 0;

  return (
    <div className="page-grid">
      <SectionHeader num="01" title="audio" />
      <div className="wave-area upload-area">
        <div className="upload-actions">
          <button className={`outline-btn ${recording ? "danger" : ""}`} onClick={toggleRecording}>
            {recording ? <Square size={15} /> : <Mic size={15} />}
            {recording ? "Stop" : "Record"}
          </button>
          <label className="outline-btn">
            <Upload size={15} />
            Upload
            <input hidden type="file" accept="audio/*" onChange={pickFile} />
          </label>
          <span className="file-name">{file?.name || "no audio selected"}</span>
        </div>
        <div className="wave-player">
          <button className="play-btn" onClick={audioPlayer.toggle} disabled={!audioUrl} title={audioPlayer.playing ? "Stop" : "Play"}>
            {audioPlayer.playing ? <Square size={15} /> : <Play size={15} />}
          </button>
          <div className="track" />
          <div className="wave-time">{formatTime(audioPlayer.currentTime)} / {formatTime(duration)}</div>
        </div>
        <canvas className="wave-canvas" ref={waveformRef} />
        <audio ref={audioRef} src={audioUrl} onLoadedMetadata={(event) => setDuration(event.currentTarget.duration || 0)} />
      </div>

      <SectionHeader num="02" title="parameters" />
      <div className="params params-listen">
        <SelectParam label="backend" value={backend} values={sttBackends.map((item) => item.name)} onChange={setBackend} accent />
        <SelectParam label="language" value="auto" values={["auto"]} onChange={() => undefined} />
      </div>

      <SectionHeader num="03" title="transcript" />
      <div className="transcript">
        {transcript || "Transcript output will appear here."}
        <div className="transcript-meta">
          Model: {backend} · Duration: {duration ? `${duration.toFixed(2)}s` : "-"} · Processing:{" "}
          {processingSeconds ? `${processingSeconds.toFixed(2)}s` : "-"} · RTF:{" "}
          {rtf ? `${rtf.toFixed(2)}x` : "-"}
        </div>
      </div>

      {error && <div className="error-line">{error}</div>}
      <button className="gen-bar" onClick={transcribe} disabled={!file}>
        <span className="gen-text">Transcribe_</span>
        <span className="gen-hint">ctrl+enter</span>
      </button>
    </div>
  );
}

function QwenStudioPage({
  backends,
  models,
  onActivity,
  onRefresh
}: {
  backends: Backend[];
  models: ModelRecord[];
  onActivity: (entry: Omit<ActivityEntry, "id" | "time">) => void;
  onRefresh: () => void;
}) {
  const [mode, setMode] = useState<"clone" | "custom" | "design">("clone");
  const [voices, setVoices] = useState<QwenVoices>({ clones: [], presets: [] });
  const [text, setText] = useState("This is Qwen Studio, rendering a high quality voice.");
  const [language, setLanguage] = useState("Auto");
  const [format, setFormat] = useState("wav");
  const [speed, setSpeed] = useState(1);
  const [modelSize, setModelSize] = useState<QwenModelSize>("1.7b");
  const [cloneVoice, setCloneVoice] = useState("");
  const [speaker, setSpeaker] = useState("Vivian");
  const [instruct, setInstruct] = useState("Speak with calm confidence and natural pacing.");
  const [designName, setDesignName] = useState("designed_voice");
  const [uploadName, setUploadName] = useState("");
  const [uploadRefText, setUploadRefText] = useState("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [prepareUpload, setPrepareUpload] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [audioUrl, setAudioUrl] = useState("");
  const [duration, setDuration] = useState(0);
  const [generationSeconds, setGenerationSeconds] = useState(0);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioPlayer = useAudioPlayer(audioRef, audioUrl);
  const waveformRef = useWaveform(audioUrl);
  const qwenBackend = backends.find((item) => item.name === "qwen3" && item.kind === "tts");
  const qwenModels = models.filter((item) => item.backend === "qwen3");
  const activeQwen = qwenModels.find((item) => item.active);
  const currentFamily = activeQwen?.id.includes("base")
    ? "base"
    : activeQwen?.id.includes("voicedesign")
      ? "voice design"
      : activeQwen?.id.includes("customvoice")
        ? "custom voice"
        : "none";

  const loadVoices = useCallback(async () => {
    try {
      setVoices(await api.qwenVoices());
    } catch (err) {
      setError(err instanceof Error ? err.message : "qwen voices failed");
    }
  }, []);

  useEffect(() => {
    loadVoices();
  }, [loadVoices]);

  useEffect(() => {
    if (!cloneVoice && voices.clones.length) setCloneVoice(voices.clones[0].name);
    if (!voices.clones.some((item) => item.name === cloneVoice) && voices.clones.length) {
      setCloneVoice(voices.clones[0].name);
    }
  }, [cloneVoice, voices.clones]);

  useEffect(() => {
    if (!voices.presets.some((item) => item.name === speaker) && voices.presets.length) {
      setSpeaker(voices.presets[0].name);
    }
  }, [speaker, voices.presets]);

  useEffect(() => {
    if (mode === "design" && modelSize !== "1.7b") {
      setModelSize("1.7b");
    }
  }, [mode, modelSize]);

  async function uploadClone(event: FormEvent) {
    event.preventDefault();
    if (!uploadName.trim() || !uploadFile) return;
    setBusy("upload");
    setError("");
    setMessage("");
    const form = new FormData();
    form.append("name", uploadName.trim());
    form.append("file", uploadFile);
    form.append("ref_text", uploadRefText);
    form.append("prepare", prepareUpload ? "true" : "false");
    form.append("model_size", modelSize);
    try {
      const res = await fetch("/v1/qwen/voices", { method: "POST", body: form });
      if (!res.ok) {
        const body = await safeJson(res);
        throw new Error(body.detail || `qwen voice upload failed: ${res.status}`);
      }
      setUploadName("");
      setUploadFile(null);
      setUploadRefText("");
      setMessage("qwen voice saved");
      await loadVoices();
      onRefresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "qwen voice upload failed");
    } finally {
      setBusy("");
    }
  }

  async function prepareClone(name: string) {
    setBusy(`prepare:${name}`);
    setError("");
    setMessage("");
    try {
      const res = await fetch(`/v1/qwen/voices/${encodeURIComponent(name)}/prepare?model_size=${encodeURIComponent(modelSize)}`, { method: "POST" });
      if (!res.ok) {
        const body = await safeJson(res);
        throw new Error(body.detail || `prepare failed: ${res.status}`);
      }
      setMessage(`${name} prepared`);
      await loadVoices();
      onRefresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "prepare failed");
    } finally {
      setBusy("");
    }
  }

  async function deleteClone(name: string) {
    setBusy(`delete:${name}`);
    setError("");
    try {
      const res = await fetch(`/v1/qwen/voices/${encodeURIComponent(name)}`, { method: "DELETE" });
      if (!res.ok) {
        const body = await safeJson(res);
        throw new Error(body.detail || `delete failed: ${res.status}`);
      }
      await loadVoices();
      onRefresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "delete failed");
    } finally {
      setBusy("");
    }
  }

  async function generate() {
    const endpoint =
      mode === "clone"
        ? "/v1/qwen/clone/speech"
        : mode === "custom"
          ? "/v1/qwen/custom-voice/speech"
          : "/v1/qwen/voice-design/speech";
    const payload =
      mode === "clone"
        ? { input: text, voice: cloneVoice, model_size: modelSize, response_format: format, speed, language }
        : mode === "custom"
          ? { input: text, speaker, model_size: modelSize, instruct, response_format: format, speed, language }
          : { input: text, instruct, model_size: "1.7b", response_format: format, speed, language };
    await generateAudio(endpoint, payload, mode);
  }

  async function saveDesignAsClone() {
    if (!designName.trim()) return;
    setBusy("save-design");
    setError("");
    setMessage("");
    try {
      const res = await fetch("/v1/qwen/voice-design/save", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          name: designName.trim(),
          input: text,
          instruct,
          model_size: "1.7b",
          speed,
          language
        })
      });
      if (!res.ok) {
        const body = await safeJson(res);
        throw new Error(body.detail || `save failed: ${res.status}`);
      }
      const body = await res.json();
      const audioRes = await fetch(`/v1/qwen/voices/${encodeURIComponent(body.name)}/reference`);
      if (audioRes.ok) {
        setOutputBlob(await audioRes.blob());
      }
      setMessage(`${body.name} saved as Qwen clone reference`);
      await loadVoices();
      onRefresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "save failed");
    } finally {
      setBusy("");
    }
  }

  async function generateAudio(endpoint: string, payload: object, label: string) {
    setBusy("generate");
    setError("");
    setMessage("");
    const start = performance.now();
    try {
      const res = await fetch(endpoint, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (!res.ok) {
        const body = await safeJson(res);
        throw new Error(body.detail || `qwen generation failed: ${res.status}`);
      }
      await setOutputBlob(await res.blob());
      const elapsed = (performance.now() - start) / 1000;
      setGenerationSeconds(elapsed);
      onActivity({
        type: "TTS",
        backend: `qwen:${label}`,
        input: text,
        duration: elapsed,
        format,
        status: "ok"
      });
      onRefresh();
    } catch (err) {
      onActivity({
        type: "TTS",
        backend: `qwen:${label}`,
        input: text,
        duration: (performance.now() - start) / 1000,
        format,
        status: "error"
      });
      setError(err instanceof Error ? err.message : "qwen generation failed");
    } finally {
      setBusy("");
    }
  }

  async function setOutputBlob(blob: Blob) {
    if (audioUrl) URL.revokeObjectURL(audioUrl);
    setAudioUrl(URL.createObjectURL(blob));
  }

  const modeHelp = {
    clone: "Use your own reference audio to imitate a saved voice.",
    custom: "Use Qwen preset voices with optional style and emotion instructions.",
    design: "Describe a new voice in text, generate it, then save it as a clone."
  }[mode];
  const canGenerate = Boolean(text.trim()) && (mode !== "clone" || Boolean(cloneVoice));
  const rtf = duration > 0 && generationSeconds > 0 ? generationSeconds / duration : 0;

  return (
    <div className="page-grid">
      <div className="stats-row qwen-stats">
        <Metric label="backend" value={qwenBackend?.enabled ? "enabled" : "disabled"} />
        <Metric label="loaded" value={qwenBackend?.loaded ? "yes" : "cold"} />
        <Metric label="active" value={currentFamily} />
        <Metric label="selected" value={mode === "design" ? "1.7b" : modelSize} />
        <Metric label="models" value={String(qwenModels.filter((item) => item.installed).length)} />
      </div>

      <SectionHeader num="01" title="mode" right={activeQwen?.id || "no qwen model active"} />
      <div className="mode-tabs">
        <button className={mode === "clone" ? "mode-tab active" : "mode-tab"} onClick={() => setMode("clone")}>
          <span className="mode-title">Clone</span>
          <span className="mode-desc">reference audio</span>
        </button>
        <button className={mode === "custom" ? "mode-tab active" : "mode-tab"} onClick={() => setMode("custom")}>
          <span className="mode-title">Preset Voice</span>
          <span className="mode-desc">voice + instructions</span>
        </button>
        <button className={mode === "design" ? "mode-tab active" : "mode-tab"} onClick={() => setMode("design")}>
          <span className="mode-title">Voice Design</span>
          <span className="mode-desc">describe a new voice</span>
        </button>
      </div>
      <div className="mode-help">{modeHelp}</div>

      <SectionHeader num="02" title="input" right={`${text.length}/4096`} />
      <textarea
        className="input-area text-input"
        maxLength={4096}
        value={text}
        onChange={(event) => setText(event.target.value)}
      />

      <SectionHeader num="03" title="qwen controls" />
      {mode === "clone" && (
        <div className="qwen-panel">
          <div className="params qwen-params">
            <SelectParam label="model" value={modelSize} values={["0.6b", "1.7b"]} onChange={(value) => setModelSize(value as QwenModelSize)} accent />
            <SelectParam label="clone voice" value={cloneVoice} values={voices.clones.map((item) => item.name)} onChange={setCloneVoice} accent />
            <SelectParam label="language" value={language} values={QWEN_LANGUAGES} onChange={setLanguage} />
            <SelectParam label="format" value={format} values={["wav", "mp3", "opus", "ogg", "flac"]} onChange={setFormat} />
            <SpeedParam speed={speed} onChange={setSpeed} />
          </div>
          <form className="clone-form qwen-upload" onSubmit={uploadClone}>
            <div className="qwen-upload-row">
              <input value={uploadName} onChange={(event) => setUploadName(event.target.value)} placeholder="qwen voice name" />
              <label className="outline-btn">
                <Upload size={15} />
                {uploadFile ? uploadFile.name : "Reference audio"}
                <input hidden type="file" accept="audio/*" onChange={(event) => setUploadFile(event.target.files?.[0] || null)} />
              </label>
              <label className="toggle-row clone-toggle">
                <input type="checkbox" checked={prepareUpload} onChange={(event) => setPrepareUpload(event.target.checked)} />
                <span>Preload</span>
              </label>
              <button className="primary-btn" disabled={busy !== "" || !uploadName.trim() || !uploadFile}>
                {busy === "upload" ? "Saving" : "Save clone"}
              </button>
            </div>
            <textarea
              className="qwen-reference-text"
              value={uploadRefText}
              onChange={(event) => setUploadRefText(event.target.value)}
              placeholder="reference transcript"
            />
          </form>
          <div className="voice-grid">
            {voices.clones.map((item) => (
              <div className="voice-card" key={item.name}>
                <div className="voice-name">{item.name}</div>
                <div className="voice-meta">{item.prepared ? "prepared" : "reference only"}</div>
                <div className="voice-actions">
                  <button className="small-btn" disabled={busy !== "" || item.prepared} onClick={() => prepareClone(item.name)}>
                    {busy === `prepare:${item.name}` ? "..." : "Preload"}
                  </button>
                  <button className="small-btn danger" disabled={busy !== ""} onClick={() => deleteClone(item.name)}>
                    <Trash2 size={13} />
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {mode === "custom" && (
        <div className="qwen-panel">
          <div className="params qwen-params">
            <SelectParam label="model" value={modelSize} values={["0.6b", "1.7b"]} onChange={(value) => setModelSize(value as QwenModelSize)} accent />
            <SelectParam label="speaker" value={speaker} values={voices.presets.map((item) => item.name)} onChange={setSpeaker} accent />
            <SelectParam label="language" value={language} values={QWEN_LANGUAGES} onChange={setLanguage} />
            <SelectParam label="format" value={format} values={["wav", "mp3", "opus", "ogg", "flac"]} onChange={setFormat} />
            <SpeedParam speed={speed} onChange={setSpeed} />
          </div>
          <textarea className="input-area text-input qwen-instruct" value={instruct} onChange={(event) => setInstruct(event.target.value)} />
        </div>
      )}

      {mode === "design" && (
        <div className="qwen-panel">
          <div className="params qwen-params">
            <SelectParam label="model" value="1.7b" values={["1.7b"]} onChange={() => setModelSize("1.7b")} accent />
            <label className="param">
              <span className="param-label">save name</span>
              <input className="qwen-inline-input" value={designName} onChange={(event) => setDesignName(event.target.value)} />
              <span className="param-underline" />
            </label>
            <SelectParam label="language" value={language} values={QWEN_LANGUAGES} onChange={setLanguage} />
            <SelectParam label="format" value={format} values={["wav", "mp3", "opus", "ogg", "flac"]} onChange={setFormat} />
            <SpeedParam speed={speed} onChange={setSpeed} />
          </div>
          <textarea className="input-area text-input qwen-instruct" value={instruct} onChange={(event) => setInstruct(event.target.value)} />
          <button className="outline-btn" disabled={busy !== "" || !designName.trim() || !text.trim() || !instruct.trim()} onClick={saveDesignAsClone}>
            {busy === "save-design" ? "Saving" : "Save as clone"}
          </button>
        </div>
      )}

      <SectionHeader num="04" title="output" right={duration ? `${duration.toFixed(1)}s` : "0.0s"} />
      <div className="wave-area">
        <div className="wave-player">
          <button className="play-btn" onClick={audioPlayer.toggle} disabled={!audioUrl} title={audioPlayer.playing ? "Stop" : "Play"}>
            {audioPlayer.playing ? <Square size={15} /> : <Play size={15} />}
          </button>
          <div className="track" />
          <div className="wave-time">{formatTime(audioPlayer.currentTime)} / {formatTime(duration)}</div>
        </div>
        <canvas className="wave-canvas" ref={waveformRef} />
        <audio ref={audioRef} src={audioUrl} onLoadedMetadata={(event) => setDuration(event.currentTarget.duration || 0)} />
      </div>

      <div className="metrics-row">
        <Metric label="generation" value={generationSeconds ? `${generationSeconds.toFixed(2)}s` : "-"} />
        <Metric label="audio" value={duration ? `${duration.toFixed(2)}s` : "-"} />
        <Metric label="rtf" value={rtf ? `${rtf.toFixed(2)}x` : "-"} />
        <Metric label="mode" value={mode} />
      </div>

      {error && <div className="error-line">{error}</div>}
      {message && <div className="ok-line">{message}</div>}
      <button className="gen-bar" onClick={generate} disabled={busy !== "" || !canGenerate}>
        <span className="gen-text">{busy === "generate" ? "Generating_" : "Generate_"}</span>
        <span className="gen-hint">qwen studio</span>
      </button>
    </div>
  );
}

function BackendsPage({ backends, onRefresh }: { backends: Backend[]; onRefresh: () => void }) {
  const tts = backends.filter((item) => item.kind === "tts");
  const stt = backends.filter((item) => item.kind === "stt");
  return (
    <div className="page-grid">
      <div className="stats-row">
        <Metric label="enabled" value={String(backends.filter((item) => item.enabled).length)} />
        <Metric label="disabled" value={String(backends.filter((item) => !item.enabled).length)} />
        <Metric label="total" value={String(backends.length)} />
        <Metric label="loaded" value={String(backends.filter((item) => item.loaded).length)} />
      </div>
      <BackendGroup title="text to speech" backends={tts} onRefresh={onRefresh} />
      <BackendGroup title="speech to text" backends={stt} onRefresh={onRefresh} />
    </div>
  );
}

function ModelsPage({ models, onRefresh }: { models: ModelRecord[]; onRefresh: () => void }) {
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const groups = ["pocket", "supertonic", "qwen3", "whisper", "parakeet"]
    .map((backend) => ({ backend, models: models.filter((item) => item.backend === backend) }))
    .filter((group) => group.models.length > 0);

  async function act(model: ModelRecord, action: "download" | "set_active") {
    setBusy(`${action}:${model.id}`);
    setError("");
    try {
      await api.modelAction(model.id, action);
      onRefresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : `${action} failed`);
    } finally {
      setBusy("");
    }
  }

  return (
    <div className="page-grid">
      <div className="stats-row">
        <Metric label="profiles" value={String(models.length)} />
        <Metric label="installed" value={String(models.filter((item) => item.installed).length)} />
        <Metric label="active" value={String(models.filter((item) => item.active).length)} />
        <Metric label="downloadable" value={String(models.filter((item) => item.downloadable).length)} />
      </div>
      {groups.map((group, index) => (
        <div key={group.backend}>
          <SectionHeader num={String(index + 1).padStart(2, "0")} title={group.backend} />
          <div className="model-list">
            {group.models.map((model) => (
              <div className={`model-card ${model.active ? "model-active" : ""}`} key={model.id}>
                <div>
                  <div className="model-title">{model.label}</div>
                  <div className="model-meta">{model.id}</div>
                  <div className="model-path">{model.path}</div>
                </div>
                <div className="model-right">
                  <span className={model.active ? "ok-text" : model.installed ? "model-state" : "err-text"}>
                    {model.active ? "active" : model.installed ? "installed" : "missing"}
                  </span>
                  <div className="backend-actions">
                    {model.downloadable && (
                      <button
                        className="small-btn"
                        disabled={busy !== ""}
                        onClick={() => act(model, "download")}
                      >
                        {busy === `download:${model.id}` ? "..." : "Download"}
                      </button>
                    )}
                    <button
                      className="small-btn"
                      disabled={busy !== "" || model.active}
                      onClick={() => act(model, "set_active")}
                    >
                      {busy === `set_active:${model.id}` ? "..." : "Set active"}
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
      {error && <div className="error-line backend-error">{error}</div>}
    </div>
  );
}

function VoicesPage({ voices, onRefresh }: { voices: Voice[]; onRefresh: () => void }) {
  const [name, setName] = useState("");
  const [backend, setBackend] = useState("pocket");
  const [file, setFile] = useState<File | null>(null);
  const [precompute, setPrecompute] = useState(true);
  const [prepareBackend, setPrepareBackend] = useState("pocket");
  const [aliasBackend, setAliasBackend] = useState("supertonic");
  const [aliasName, setAliasName] = useState("");
  const [aliasTarget, setAliasTarget] = useState("");
  const [busy, setBusy] = useState(false);
  const [aliasBusy, setAliasBusy] = useState(false);
  const [prepareBusy, setPrepareBusy] = useState("");
  const [loadingPreview, setLoadingPreview] = useState("");
  const [activePreview, setActivePreview] = useState("");
  const [error, setError] = useState("");
  const previewAudioRef = useRef<HTMLAudioElement | null>(null);
  const cloned = voices.filter((voice) => voice.type === "cloned");
  const presets = voices.filter((voice) => voice.type === "preset");
  const aliases = voices.filter((voice) => voice.type === "alias");
  const ttsBackends = [...new Set(voices.filter((voice) => voice.backend).map((voice) => voice.backend as string))];
  const aliasTargetOptions = voices
    .filter((voice) => voice.backend === aliasBackend && voice.type !== "alias")
    .map((voice) => voice.name);

  useEffect(() => {
    const audio = previewAudioRef.current;
    if (!audio) return;
    const clear = () => setActivePreview("");
    audio.addEventListener("ended", clear);
    audio.addEventListener("pause", clear);
    return () => {
      audio.removeEventListener("ended", clear);
      audio.removeEventListener("pause", clear);
    };
  }, []);

  async function upload(event: FormEvent) {
    event.preventDefault();
    if (!file || !name.trim()) return;
    setBusy(true);
    setError("");
    const form = new FormData();
    form.append("name", name.trim());
    form.append("backend", backend);
    form.append("precompute", precompute ? "true" : "false");
    form.append("file", file);
    try {
      const res = await fetch("/v1/voices", { method: "POST", body: form });
      if (!res.ok) {
        const body = await safeJson(res);
        throw new Error(body.detail || `upload failed: ${res.status}`);
      }
      const body = await res.json();
      if (body.precompute_error) {
        setError(`Voice saved, but precompute failed: ${body.precompute_error}`);
      }
      setName("");
      setFile(null);
      onRefresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "upload failed");
    } finally {
      setBusy(false);
    }
  }

  async function remove(voice: string) {
    await fetch(`/v1/voices/${encodeURIComponent(voice)}`, { method: "DELETE" });
    onRefresh();
  }

  async function saveAlias(event: FormEvent) {
    event.preventDefault();
    if (!aliasBackend || !aliasName.trim() || !aliasTarget.trim()) return;
    setAliasBusy(true);
    setError("");
    try {
      await api.setVoiceAlias(aliasBackend, aliasName.trim(), aliasTarget.trim());
      setAliasName("");
      setAliasTarget("");
      onRefresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "alias save failed");
    } finally {
      setAliasBusy(false);
    }
  }

  async function removeAlias(voice: Voice) {
    if (!voice.backend) return;
    setError("");
    try {
      await api.deleteVoiceAlias(voice.backend, voice.name);
      onRefresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "alias delete failed");
    }
  }

  async function prepare(voice: Voice) {
    setPrepareBusy(voice.name);
    setError("");
    try {
      await api.prepareVoice(voice.name, prepareBackend);
      onRefresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "voice prepare failed");
    } finally {
      setPrepareBusy("");
    }
  }

  async function preview(voice: Voice) {
    const key = voice.type === "cloned" ? `clone:${voice.name}` : `${voice.backend}:${voice.name}`;
    const audio = previewAudioRef.current;
    if (activePreview === key && audio && !audio.paused) {
      stopPreview(audio);
      setActivePreview("");
      return;
    }
    setLoadingPreview(key);
    setError("");
    try {
      let blob: Blob;
      if (voice.type === "cloned") {
        const res = await fetch(`/v1/voices/${encodeURIComponent(voice.name)}/reference`);
        if (!res.ok) {
          const body = await safeJson(res);
          throw new Error(body.detail || `preview failed: ${res.status}`);
        }
        blob = await res.blob();
      } else {
        const res = await fetch("/v1/audio/speech", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            model: voice.backend,
            input: `This is ${voice.name}, previewing in Timbre.`,
            voice: voice.name,
            response_format: "wav",
            speed: 1
          })
        });
        if (!res.ok) {
          const body = await safeJson(res);
          throw new Error(body.detail || `preview failed: ${res.status}`);
        }
        blob = await res.blob();
      }
      await playPreviewBlob(blob, previewAudioRef);
      setActivePreview(key);
    } catch (err) {
      setError(err instanceof Error ? err.message : "preview failed");
    } finally {
      setLoadingPreview("");
    }
  }

  return (
    <div className="page-grid">
      <SectionHeader num="01" title="new clone" />
      <form className="clone-form" onSubmit={upload}>
        <input value={name} onChange={(event) => setName(event.target.value)} placeholder="voice name" />
        <select value={backend} onChange={(event) => setBackend(event.target.value)}>
          <option value="pocket">pocket</option>
          <option value="supertonic">supertonic</option>
        </select>
        <label className="outline-btn">
          <Upload size={15} />
          {file ? file.name : "Reference"}
          <input hidden type="file" accept="audio/*,.json" onChange={(event) => setFile(event.target.files?.[0] || null)} />
        </label>
        <label className="toggle-row clone-toggle">
          <input type="checkbox" checked={precompute} onChange={(event) => setPrecompute(event.target.checked)} />
          <span>Precompute</span>
        </label>
        <button className="primary-btn" disabled={busy || !name || !file}>
          {busy ? "Processing" : "Create"}
        </button>
      </form>
      {error && <div className="error-line">{error}</div>}

      <SectionHeader num="02" title="aliases" right={`${aliases.length}`} />
      <form className="clone-form" onSubmit={saveAlias}>
        <select value={aliasBackend} onChange={(event) => setAliasBackend(event.target.value)}>
          {(ttsBackends.length ? ttsBackends : ["pocket", "supertonic"]).map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
        <input
          value={aliasName}
          onChange={(event) => setAliasName(event.target.value)}
          placeholder="alias name"
        />
        <input
          list="voice-targets"
          value={aliasTarget}
          onChange={(event) => setAliasTarget(event.target.value)}
          placeholder="target voice"
        />
        <datalist id="voice-targets">
          {aliasTargetOptions.map((name) => (
            <option key={name} value={name} />
          ))}
        </datalist>
        <button className="primary-btn" disabled={aliasBusy || !aliasName || !aliasTarget}>
          {aliasBusy ? "Saving" : "Save alias"}
        </button>
      </form>
      <div className="voice-grid">
        {aliases.map((voice) => (
          <div className="voice-card" key={`${voice.backend}-${voice.name}`}>
            <div className="voice-name">{voice.name}</div>
            <div className="voice-meta">
              {voice.backend} -&gt; {voice.target}
            </div>
            <div className="voice-actions">
              <button
                className="small-btn"
                onClick={() => preview(voice)}
                disabled={loadingPreview !== ""}
                title="Preview"
              >
                {activePreview === `${voice.backend}:${voice.name}` ? <Square size={13} /> : <Play size={13} />}
                {loadingPreview === `${voice.backend}:${voice.name}`
                  ? "..."
                  : activePreview === `${voice.backend}:${voice.name}`
                    ? "Stop"
                    : "Preview"}
              </button>
              <button className="small-btn danger" onClick={() => removeAlias(voice)}>
                <Trash2 size={13} />
                Delete
              </button>
            </div>
          </div>
        ))}
      </div>

      <SectionHeader
        num="03"
        title="cloned"
        right={
          <select value={prepareBackend} onChange={(event) => setPrepareBackend(event.target.value)}>
            {(ttsBackends.length ? ttsBackends : ["pocket", "supertonic"]).map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        }
      />
      <div className="voice-grid">
        {cloned.map((voice) => (
          <div className="voice-card" key={voice.name}>
            <div className="voice-name">{voice.name}</div>
            <div className="voice-meta">{voice.prepared_backends?.join(", ") || "reference only"}</div>
            <div className="voice-actions">
              <button
                className="small-btn"
                onClick={() => preview(voice)}
                disabled={loadingPreview !== ""}
                title="Preview"
              >
                {activePreview === `clone:${voice.name}` ? <Square size={13} /> : <Play size={13} />}
                {loadingPreview === `clone:${voice.name}`
                  ? "..."
                  : activePreview === `clone:${voice.name}`
                    ? "Stop"
                  : "Preview"}
              </button>
              <button
                className="small-btn"
                onClick={() => prepare(voice)}
                disabled={prepareBusy !== "" || voice.prepared_backends?.includes(prepareBackend)}
                title="Prepare voice"
              >
                {prepareBusy === voice.name ? "..." : "Prepare"}
              </button>
              <button className="small-btn danger" onClick={() => remove(voice.name)}>
                <Trash2 size={13} />
                Delete
              </button>
            </div>
          </div>
        ))}
      </div>

      <SectionHeader num="04" title="presets" right={`${presets.length}`} />
      <div className="voice-grid">
        {presets.map((voice) => (
          <div className="voice-card" key={`${voice.backend}-${voice.name}`}>
            <div className="voice-name">{voice.name}</div>
            <div className="voice-meta">{voice.backend} · built-in</div>
            <button
              className="small-btn"
              onClick={() => preview(voice)}
              disabled={loadingPreview !== ""}
              title="Preview"
            >
              {activePreview === `${voice.backend}:${voice.name}` ? <Square size={13} /> : <Play size={13} />}
              {loadingPreview === `${voice.backend}:${voice.name}`
                ? "..."
                : activePreview === `${voice.backend}:${voice.name}`
                  ? "Stop"
                  : "Preview"}
            </button>
          </div>
        ))}
      </div>
      <audio ref={previewAudioRef} />
    </div>
  );
}

function ConfigPage({ backends, onRefresh }: { backends: Backend[]; onRefresh: () => void }) {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [configPath, setConfigPath] = useState("");
  const [optionText, setOptionText] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    api.config()
      .then((body) => {
        if (cancelled) return;
        setConfig(body.config);
        setConfigPath(body.path);
        setOptionText(optionTextForConfig(body.config));
      })
      .catch((err) => setError(err instanceof Error ? err.message : "config load failed"));
    return () => {
      cancelled = true;
    };
  }, []);

  async function save() {
    if (!config) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const body = await api.saveConfig(configWithOptions(config, optionText));
      setConfig(body.config);
      setConfigPath(body.path);
      setOptionText(optionTextForConfig(body.config));
      setMessage("saved");
      onRefresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "config save failed");
    } finally {
      setBusy(false);
    }
  }

  if (!config) {
    return (
      <div className="page-grid">
        <SectionHeader num="01" title="config" />
        <div className="config-box">{error || "loading"}</div>
      </div>
    );
  }

  const backendNames = backends.map((item) => item.name).join(", ") || "none";

  return (
    <div className="page-grid">
      <SectionHeader num="01" title="runtime" right={configPath} />
      <div className="config-grid">
        <label className="config-field">
          <span>host</span>
          <input
            value={config.server.host}
            onChange={(event) =>
              setConfig({ ...config, server: { ...config.server, host: event.target.value } })
            }
          />
        </label>
        <label className="config-field">
          <span>port</span>
          <input
            type="number"
            min="1"
            max="65535"
            value={config.server.port}
            onChange={(event) =>
              setConfig({ ...config, server: { ...config.server, port: Number(event.target.value) } })
            }
          />
        </label>
        <label className="config-field">
          <span>ttl sweep</span>
          <input
            type="number"
            min="1"
            value={config.server.ttl_check_interval}
            onChange={(event) =>
              setConfig({
                ...config,
                server: { ...config.server, ttl_check_interval: Number(event.target.value) }
              })
            }
          />
        </label>
        <label className="config-field wide">
          <span>voices dir</span>
          <input
            value={config.voices.dir}
            onChange={(event) =>
              setConfig({ ...config, voices: { ...config.voices, dir: event.target.value } })
            }
          />
        </label>
      </div>

      <SectionHeader num="02" title="defaults" right={`active: ${backendNames}`} />
      <div className="config-grid defaults-grid">
        <label className="config-field">
          <span>tts default</span>
          <select
            value={config.tts.default}
            onChange={(event) =>
              setConfig({ ...config, tts: { ...config.tts, default: event.target.value } })
            }
          >
            {Object.keys(config.tts.backends).map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <label className="config-field">
          <span>stt default</span>
          <select
            value={config.stt.default}
            onChange={(event) =>
              setConfig({ ...config, stt: { ...config.stt, default: event.target.value } })
            }
          >
            {Object.keys(config.stt.backends).map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label>
      </div>

      <ConfigBackendGroup
        title="text to speech"
        groupName="tts"
        group={config.tts}
        optionText={optionText}
        onCoreChange={(name, patch) =>
          setConfig({ ...config, tts: patchBackend(config.tts, name, patch) })
        }
        onOptionsChange={(key, value) => setOptionText({ ...optionText, [key]: value })}
      />
      <ConfigBackendGroup
        title="speech to text"
        groupName="stt"
        group={config.stt}
        optionText={optionText}
        onCoreChange={(name, patch) =>
          setConfig({ ...config, stt: patchBackend(config.stt, name, patch) })
        }
        onOptionsChange={(key, value) => setOptionText({ ...optionText, [key]: value })}
      />

      {error && <div className="error-line">{error}</div>}
      {message && <div className="ok-line">{message}</div>}
      <button className="gen-bar" onClick={save} disabled={busy}>
        <span className="gen-text">{busy ? "Saving_" : "Save config_"}</span>
        <span className="gen-hint">writes yaml</span>
      </button>
    </div>
  );
}

function ConfigBackendGroup({
  title,
  groupName,
  group,
  optionText,
  onCoreChange,
  onOptionsChange
}: {
  title: string;
  groupName: "tts" | "stt";
  group: ConfigGroup;
  optionText: Record<string, string>;
  onCoreChange: (name: string, patch: Partial<BackendSettings>) => void;
  onOptionsChange: (key: string, value: string) => void;
}) {
  return (
    <div>
      <SectionHeader num={groupName === "tts" ? "03" : "04"} title={title} />
      <div className="config-backends">
        {Object.entries(group.backends).map(([name, backend]) => {
          const key = `${groupName}.${name}`;
          return (
            <div className="config-backend-card" key={key}>
              <div className="config-backend-head">
                <label className="toggle-row">
                  <input
                    type="checkbox"
                    checked={backend.enabled}
                    onChange={(event) => onCoreChange(name, { enabled: event.target.checked })}
                  />
                  <span>{name}</span>
                </label>
                <span className={backend.enabled ? "ok-text" : "err-text"}>
                  {backend.enabled ? "enabled" : "disabled"}
                </span>
              </div>
              <div className="config-grid compact">
                <label className="config-field">
                  <span>device</span>
                  <input
                    value={backend.device}
                    onChange={(event) => onCoreChange(name, { device: event.target.value })}
                  />
                </label>
                <label className="config-field">
                  <span>ttl</span>
                  <input
                    type="number"
                    min="0"
                    value={backend.ttl}
                    onChange={(event) => onCoreChange(name, { ttl: Number(event.target.value) })}
                  />
                </label>
              </div>
              <details className="advanced-options">
                <summary>Advanced options</summary>
                <label className="config-field options-field">
                  <span>raw options</span>
                  <textarea
                    value={optionText[key] || "{}"}
                    onChange={(event) => onOptionsChange(key, event.target.value)}
                  />
                </label>
              </details>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ApiPage({ backends, voices }: { backends: Backend[]; voices: Voice[] }) {
  const baseUrl = "http://127.0.0.1:9000";
  const enabledTts = backends.filter((item) => item.kind === "tts" && item.enabled).map((item) => item.name);
  const enabledStt = backends.filter((item) => item.kind === "stt" && item.enabled).map((item) => item.name);
  const allTts = backends.filter((item) => item.kind === "tts").map((item) => item.name);
  const allStt = backends.filter((item) => item.kind === "stt").map((item) => item.name);
  const voiceNames = voices.map((item) => item.name);
  const sampleTts = enabledTts[0] || allTts[0] || "pocket";
  const sampleStt = enabledStt[0] || allStt[0] || "parakeet";
  const sampleVoices = voices.filter(
    (item) =>
      item.backend === sampleTts ||
      (item.type === "cloned" && item.prepared_backends?.includes(sampleTts))
  );
  const sampleVoice = sampleVoices[0]?.name || "default";
  const sampleAliasTarget = sampleVoices.find((item) => item.type !== "alias")?.name || sampleVoice;

  return (
    <div className="page-grid">
      <SectionHeader num="01" title="base url" right="swap host for tailscale" />
      <div className="api-grid">
        <ApiInfo label="local" value={baseUrl} />
        <ApiInfo label="ui" value={`${baseUrl}/ui/`} />
        <ApiInfo label="openapi" value={`${baseUrl}/docs`} />
        <ApiInfo label="tts models" value={enabledTts.join(", ") || "none enabled"} />
        <ApiInfo label="stt models" value={enabledStt.join(", ") || "none enabled"} />
        <ApiInfo label="voices" value={voiceNames.slice(0, 8).join(", ") || "none"} />
      </div>

      <SectionHeader num="02" title="discovery" />
      <ApiCode title="Health" code={`curl ${baseUrl}/health`} />
      <ApiCode title="Models" code={`curl ${baseUrl}/v1/models`} />
      <ApiCode title="Backends" code={`curl ${baseUrl}/v1/backends`} />
      <ApiCode title="Voices" code={`curl ${baseUrl}/v1/voices`} />

      <SectionHeader num="03" title="text to speech" />
      <ApiCode
        title="Generate speech"
        code={`curl ${baseUrl}/v1/audio/speech \\
  -H "content-type: application/json" \\
  -d '{
    "model": "${sampleTts}",
    "input": "Hello from Timbre.",
    "voice": "${sampleVoice}",
    "response_format": "wav",
    "speed": 1.0,
    "language": "en",
    "steps": 8
  }' \\
  --output timbre.wav`}
      />
      <ApiNote text="For TTS, model is the backend name. Use pocket, supertonic, or qwen3 when enabled. response_format accepts wav, mp3, opus, ogg, or flac. language and steps are backend-specific fields used by some backends." />

      <SectionHeader num="04" title="speech to text" />
      <ApiCode
        title="Transcribe audio"
        code={`curl ${baseUrl}/v1/audio/transcriptions \\
  -F model=${sampleStt} \\
  -F file=@sample.wav`}
      />
      <ApiNote text="For STT, model is the backend name. Use parakeet or whisper when enabled. Optional form fields include language and prompt." />

      <SectionHeader num="05" title="backend control" />
      <ApiCode
        title="Load or unload a backend"
        code={`curl ${baseUrl}/v1/backends/tts/${sampleTts} \\
  -H "content-type: application/json" \\
  -d '{"action":"load"}'

curl ${baseUrl}/v1/backends/stt/${sampleStt} \\
  -H "content-type: application/json" \\
  -d '{"action":"unload"}'`}
      />
      <ApiCode
        title="Enable or disable a backend"
        code={`curl ${baseUrl}/v1/backends/tts/${sampleTts} \\
  -H "content-type: application/json" \\
  -d '{"action":"enable"}'

curl ${baseUrl}/v1/backends/stt/${sampleStt} \\
  -H "content-type: application/json" \\
  -d '{"action":"disable"}'`}
      />
      <ApiNote text="Use /tts/name for text-to-speech backends and /stt/name for speech-to-text backends. load/unload changes runtime memory; enable/disable updates config and rebuilds the manager." />

      <SectionHeader num="06" title="voices and config" />
      <ApiCode
        title="Upload a cloned voice"
        code={`curl ${baseUrl}/v1/voices \\
  -F name=my_voice \\
  -F backend=${sampleTts} \\
  -F precompute=true \\
  -F file=@reference.wav`}
      />
      <ApiCode
        title="Preview or delete a cloned voice"
        code={`curl ${baseUrl}/v1/voices/my_voice/reference --output reference.wav
curl -X DELETE ${baseUrl}/v1/voices/my_voice`}
      />
      <ApiCode
        title="Set or delete a voice alias"
        code={`curl ${baseUrl}/v1/voices/aliases \\
  -H "content-type: application/json" \\
  -d '{"backend":"${sampleTts}","alias":"friendly","target":"${sampleAliasTarget}"}'

curl -X DELETE ${baseUrl}/v1/voices/aliases/${sampleTts}/friendly`}
      />
      <ApiNote text="Aliases are backend-scoped. A request can send voice=friendly while Timbre resolves it to the configured target voice before calling that backend." />
      <ApiCode
        title="Read or replace config"
        code={`curl ${baseUrl}/v1/config

curl -X PUT ${baseUrl}/v1/config \\
  -H "content-type: application/json" \\
  -d @config.json`}
      />
    </div>
  );
}

function ApiInfo({ label, value }: { label: string; value: string }) {
  return (
    <div className="api-info">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function ApiCode({ title, code }: { title: string; code: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    if (navigator.clipboard) {
      await navigator.clipboard.writeText(code).catch(() => undefined);
    }
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1200);
  }

  return (
    <div className="api-card">
      <div className="api-card-head">
        <div>{title}</div>
        <button className="small-btn" onClick={copy}>
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre>{code}</pre>
    </div>
  );
}

function ApiNote({ text }: { text: string }) {
  return <div className="api-note">{text}</div>;
}

function LogPage({ activity }: { activity: ActivityEntry[] }) {
  return (
    <div className="page-grid">
      <SectionHeader num="01" title="activity log" right={`${activity.length}`} />
      <div className="log-table">
        <div className="log-row log-head">
          <span>Time</span>
          <span>Type</span>
          <span>Backend</span>
          <span>Input</span>
          <span>Duration</span>
          <span>Format</span>
          <span>Status</span>
        </div>
        {activity.length === 0 && <div className="empty-log">No UI requests yet.</div>}
        {activity.map((entry) => (
          <div className="log-row" key={entry.id}>
            <span>{entry.time}</span>
            <span className={`log-badge ${entry.type.toLowerCase()}`}>{entry.type}</span>
            <span>{entry.backend}</span>
            <span title={entry.input}>{truncate(entry.input, 42)}</span>
            <span>{entry.duration.toFixed(2)}s</span>
            <span>{entry.format}</span>
            <span className={entry.status === "ok" ? "ok-text" : "err-text"}>{entry.status}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function CompactActivityLog({ activity }: { activity: ActivityEntry[] }) {
  return (
    <div className="rail-panel activity-panel">
      <div className="rail-header">activity</div>
      <div className="activity-list">
        {activity.length === 0 && <div className="activity-empty">No requests yet.</div>}
        {activity.slice(0, 20).map((entry) => (
          <div className="activity-entry" key={entry.id}>
            <span className="activity-time">{entry.time}</span>
            <span className={`log-badge ${entry.type.toLowerCase()}`}>{entry.type}</span>
            <span className="activity-backend">{entry.backend}</span>
            <span className={entry.status === "ok" ? "activity-duration" : "activity-duration err-text"}>
              {entry.duration.toFixed(2)}s
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function WireframeSphere({ energyRef }: { energyRef: React.MutableRefObject<number> }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let raf = 0;
    let energy = 0;
    let targetEnergy = 0;
    let nextPulse = performance.now() + randomBetween(3000, 5000);
    let glitchFrames = 0;
    let lastGhost = 0;
    const ghosts: { at: number; points: ProjectedPoint[] }[] = [];

    const drawFrame = (t: number) => {
      const rect = canvas.getBoundingClientRect();
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      const width = Math.max(1, Math.floor(rect.width * dpr));
      const height = Math.max(1, Math.floor(rect.height * dpr));
      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width;
        canvas.height = height;
      }

      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, rect.width, rect.height);

      if (t > nextPulse) {
        targetEnergy = randomBetween(0.6, 1.0);
        nextPulse = t + randomBetween(3000, 5000);
        glitchFrames = Math.random() > 0.5 ? 2 : 1;
      }

      targetEnergy *= 0.92;
      if (targetEnergy < 0.02) targetEnergy = 0;
      const audioEnergy = Math.min(1, Math.max(0, energyRef.current));
      energy += (Math.max(targetEnergy, audioEnergy) - energy) * 0.08;
      if (audioEnergy > 0.34 && glitchFrames === 0 && Math.random() > 0.92) {
        glitchFrames = 1;
      }

      const points = projectSphere(t, rect.width, rect.height, energy);
      if (energy > 0.35 && t - lastGhost > 300) {
        ghosts.unshift({ at: t, points });
        ghosts.splice(3);
        lastGhost = t;
      }

      drawGhosts(ctx, ghosts, t);
      drawSphere(ctx, points);
      drawScanlines(ctx, rect.width, rect.height, t);
      if (glitchFrames > 0) {
        applyGlitch(ctx, canvas.width, canvas.height, dpr);
        glitchFrames -= 1;
      }

      raf = requestAnimationFrame(drawFrame);
    };

    raf = requestAnimationFrame(drawFrame);
    return () => cancelAnimationFrame(raf);
  }, []);

  return (
    <div className="rail-panel viz-panel">
      <div className="rail-header">visualization</div>
      <canvas className="sphere-canvas" ref={canvasRef} />
    </div>
  );
}

type ProjectedPoint = {
  x: number;
  y: number;
  depth: number;
  lat: number;
  lon: number;
};

function projectSphere(t: number, width: number, height: number, energy: number): ProjectedPoint[] {
  const latSegments = 18;
  const lonSegments = 26;
  const radius = Math.min(115, Math.min(width, height) * 0.38);
  const rotY = t * 0.00012;
  const breath = 1 + Math.sin(t * 0.0008) * 0.015;
  const points: ProjectedPoint[] = [];
  for (let lat = 0; lat <= latSegments; lat++) {
    const theta = (lat / latSegments) * Math.PI;
    for (let lon = 0; lon < lonSegments; lon++) {
      const phi = (lon / lonSegments) * Math.PI * 2;
      const distortion = 1 + energy * 0.4 * Math.sin(phi * 3 + t * 0.004) * Math.cos(theta * 2);
      const x0 = Math.sin(theta) * Math.cos(phi) * distortion;
      const y0 = Math.cos(theta) * (1 + energy * 0.12 * Math.sin(phi * 2));
      const z0 = Math.sin(theta) * Math.sin(phi) * distortion;
      const x = x0 * Math.cos(rotY) + z0 * Math.sin(rotY);
      const z = -x0 * Math.sin(rotY) + z0 * Math.cos(rotY);
      const perspective = 1 / (1.9 - z * 0.55);
      points.push({
        x: width / 2 + x * radius * breath * perspective,
        y: height / 2 + y0 * radius * breath * perspective,
        depth: (z + 1) / 2,
        lat,
        lon
      });
    }
  }
  return points;
}

function drawSphere(ctx: CanvasRenderingContext2D, points: ProjectedPoint[]) {
  ctx.lineWidth = 0.55;
  drawSphereLines(ctx, points, "#e07845", 1);
  for (const point of points) {
    if (point.depth <= 0.45) continue;
    ctx.globalAlpha = Math.min(0.85, 0.22 + point.depth * 0.58);
    ctx.fillStyle = "#e07845";
    ctx.beginPath();
    ctx.arc(point.x, point.y, 0.5 + point.depth * 1.2, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.globalAlpha = 1;
}

function drawGhosts(
  ctx: CanvasRenderingContext2D,
  ghosts: { at: number; points: ProjectedPoint[] }[],
  t: number
) {
  ghosts.forEach((ghost, index) => {
    const age = t - ghost.at;
    if (age > 1200) return;
    ctx.lineWidth = 0.35;
    const opacity = (1 - age / 1200) * 0.55;
    drawSphereLines(ctx, ghost.points, index === 0 ? "#b85e35" : "#7a3f22", opacity);
  });
}

function drawSphereLines(
  ctx: CanvasRenderingContext2D,
  points: ProjectedPoint[],
  color: string,
  opacity: number
) {
  const lonSegments = 26;
  const latSegments = 18;
  ctx.strokeStyle = color;
  for (let lat = 0; lat <= latSegments; lat++) {
    for (let lon = 0; lon < lonSegments; lon++) {
      const a = points[lat * lonSegments + lon];
      const b = points[lat * lonSegments + ((lon + 1) % lonSegments)];
      strokeSegment(ctx, a, b, opacity);
    }
  }
  for (let lon = 0; lon < lonSegments; lon++) {
    for (let lat = 0; lat < latSegments; lat++) {
      const a = points[lat * lonSegments + lon];
      const b = points[(lat + 1) * lonSegments + lon];
      strokeSegment(ctx, a, b, opacity);
    }
  }
  ctx.globalAlpha = 1;
}

function strokeSegment(ctx: CanvasRenderingContext2D, a: ProjectedPoint, b: ProjectedPoint, opacity: number) {
  const depth = (a.depth + b.depth) / 2;
  ctx.globalAlpha = opacity * (0.16 + depth * 0.55);
  ctx.beginPath();
  ctx.moveTo(a.x, a.y);
  ctx.lineTo(b.x, b.y);
  ctx.stroke();
}

function drawScanlines(ctx: CanvasRenderingContext2D, width: number, height: number, t: number) {
  ctx.globalAlpha = 0.025;
  ctx.fillStyle = "#ffffff";
  for (let y = 0; y < height; y += 3) ctx.fillRect(0, y, width, 1);
  ctx.globalAlpha = 0.04;
  ctx.fillStyle = "#e07845";
  ctx.fillRect(0, (t * 0.015) % height, width, 2);
  ctx.globalAlpha = 1;
}

function applyGlitch(ctx: CanvasRenderingContext2D, width: number, height: number, dpr: number) {
  const slices = 2 + Math.floor(Math.random() * 3);
  for (let i = 0; i < slices; i++) {
    const sliceHeight = Math.floor(randomBetween(2, 8) * dpr);
    const y = Math.floor(Math.random() * Math.max(1, height - sliceHeight));
    const shift = Math.floor(randomBetween(1, 3) * dpr) * (Math.random() > 0.5 ? 1 : -1);
    const image = ctx.getImageData(0, y, width, sliceHeight);
    ctx.putImageData(image, shift, y);
  }
}

function BackendGroup({
  title,
  backends,
  onRefresh
}: {
  title: string;
  backends: Backend[];
  onRefresh: () => void;
}) {
  const [busyKey, setBusyKey] = useState("");
  const [error, setError] = useState("");

  async function run(backend: Backend, action: "load" | "unload" | "enable" | "disable") {
    setBusyKey(`${backend.kind}.${backend.name}.${action}`);
    setError("");
    try {
      await api.backendAction(backend.kind, backend.name, action);
      onRefresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : `${action} failed`);
    } finally {
      setBusyKey("");
    }
  }

  return (
    <div>
      <SectionHeader num={title.startsWith("text") ? "01" : "02"} title={title} />
      <div className="backend-list">
        {backends.map((backend) => (
          <div className={`backend-card ${backend.enabled ? "" : "backend-disabled"}`} key={backend.name}>
            <div>
              <div className="backend-title">{backend.name}</div>
              <div className="backend-meta">
                {backend.device} · TTL: {backend.ttl === 0 ? "keep warm" : `${backend.ttl}s`}
              </div>
            </div>
            <div className="backend-right">
              <div className={backend.enabled ? "backend-state loaded" : "backend-state idle"}>
                <span className={backend.enabled ? "dot-g" : "dot-r"} />
                {backend.enabled ? "enabled" : "disabled"}
              </div>
              <div className={backend.loaded ? "backend-state loaded" : "backend-state idle"}>
                <span className={backend.loaded ? "dot-g" : "dot-r"} />
                {backend.loaded ? "loaded" : "cold"}
              </div>
              <div className="backend-actions">
                <button
                  className="small-btn"
                  onClick={() => run(backend, backend.enabled ? "disable" : "enable")}
                  disabled={busyKey !== ""}
                >
                  {busyKey === `${backend.kind}.${backend.name}.${backend.enabled ? "disable" : "enable"}`
                    ? "..."
                    : backend.enabled
                      ? "Disable"
                      : "Enable"}
                </button>
                <button
                  className="small-btn"
                  onClick={() => run(backend, backend.loaded ? "unload" : "load")}
                  disabled={busyKey !== "" || !backend.enabled}
                >
                  {busyKey === `${backend.kind}.${backend.name}.${backend.loaded ? "unload" : "load"}`
                    ? "..."
                    : backend.loaded
                      ? "Unload"
                      : "Load"}
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
      {error && <div className="error-line backend-error">{error}</div>}
    </div>
  );
}

function SectionHeader({ num, title, right }: { num: string; title: string; right?: React.ReactNode }) {
  return (
    <div className="sec-header">
      <span>
        <span className="sec-num">{num}</span> — {title}
      </span>
      {right && <span>{right}</span>}
    </div>
  );
}

function SelectParam({
  label,
  value,
  values,
  onChange,
  accent
}: {
  label: string;
  value: string;
  values: string[];
  onChange: (value: string) => void;
  accent?: boolean;
}) {
  return (
    <label className="param">
      <span className="param-label">{label}</span>
      <select className={`param-select ${accent ? "param-value-acc" : ""}`} value={value} onChange={(event) => onChange(event.target.value)}>
        {values.map((item) => (
          <option key={item} value={item}>
            {item}
          </option>
        ))}
      </select>
      <span className="param-underline" />
    </label>
  );
}

function SpeedParam({ speed, onChange }: { speed: number; onChange: (value: number) => void }) {
  return (
    <div className="param">
      <div className="param-label">speed</div>
      <div className="slider-row">
        <input className="range" type="range" min="0.5" max="1.5" step="0.05" value={speed} onChange={(event) => onChange(Number(event.target.value))} />
        <div className="slider-val">{speed.toFixed(2)}</div>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value}</div>
    </div>
  );
}

function useAudioPlayer(audioRef: React.MutableRefObject<HTMLAudioElement | null>, audioUrl: string) {
  const [playing, setPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    const syncTime = () => setCurrentTime(audio.currentTime || 0);
    const onPlay = () => setPlaying(true);
    const onStop = () => {
      setPlaying(false);
      syncTime();
    };

    audio.addEventListener("play", onPlay);
    audio.addEventListener("pause", onStop);
    audio.addEventListener("ended", onStop);
    audio.addEventListener("timeupdate", syncTime);
    return () => {
      audio.removeEventListener("play", onPlay);
      audio.removeEventListener("pause", onStop);
      audio.removeEventListener("ended", onStop);
      audio.removeEventListener("timeupdate", syncTime);
    };
  }, [audioRef, audioUrl]);

  useEffect(() => {
    setPlaying(false);
    setCurrentTime(0);
  }, [audioUrl]);

  function stop() {
    const audio = audioRef.current;
    if (!audio) return;
    audio.pause();
    audio.currentTime = 0;
    setPlaying(false);
    setCurrentTime(0);
  }

  function toggle() {
    const audio = audioRef.current;
    if (!audio) return;
    if (!audio.paused && !audio.ended) {
      stop();
      return;
    }
    audio.play().catch(() => undefined);
  }

  return { currentTime, playing, toggle };
}

function useAudioEnergy(
  audioRef: React.MutableRefObject<HTMLAudioElement | null>,
  audioUrl: string,
  generating: boolean
) {
  const energyRef = useRef(0);
  const graphRef = useRef<{
    context: AudioContext;
    analyser: AnalyserNode;
    data: Uint8Array<ArrayBuffer>;
  } | null>(null);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    let raf = 0;

    function ensureGraph() {
      if (graphRef.current || !audio) return graphRef.current;
      const context = new AudioContext();
      const source = context.createMediaElementSource(audio);
      const analyser = context.createAnalyser();
      analyser.fftSize = 256;
      analyser.smoothingTimeConstant = 0.62;
      source.connect(analyser);
      analyser.connect(context.destination);
      graphRef.current = {
        context,
        analyser,
        data: new Uint8Array(new ArrayBuffer(analyser.frequencyBinCount))
      };
      return graphRef.current;
    }

    function sample(t: number) {
      let target = generating ? 0.36 + Math.sin(t * 0.018) * 0.12 : 0;
      const graph = graphRef.current;
      if (graph && audio && !audio.paused && !audio.ended) {
        graph.analyser.getByteTimeDomainData(graph.data);
        let sum = 0;
        for (const value of graph.data) {
          const centered = (value - 128) / 128;
          sum += centered * centered;
        }
        target = Math.max(target, Math.min(1, Math.sqrt(sum / graph.data.length) * 7));
      }
      energyRef.current += (target - energyRef.current) * 0.22;
      raf = requestAnimationFrame(sample);
    }

    const onPlay = () => {
      const graph = ensureGraph();
      graph?.context.resume().catch(() => undefined);
    };

    audio.addEventListener("play", onPlay);
    raf = requestAnimationFrame(sample);
    return () => {
      audio.removeEventListener("play", onPlay);
      cancelAnimationFrame(raf);
    };
  }, [audioRef, audioUrl, generating]);

  return energyRef;
}

function useWaveform(audioUrl: string) {
  const ref = useRef<HTMLCanvasElement | null>(null);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const target = canvas;
    let cancelled = false;

    async function draw() {
      const ctx = target.getContext("2d");
      if (!ctx) return;
      const rect = target.getBoundingClientRect();
      const ratio = window.devicePixelRatio || 1;
      target.width = Math.max(1, Math.floor(rect.width * ratio));
      target.height = Math.max(1, Math.floor(rect.height * ratio));
      ctx.scale(ratio, ratio);
      ctx.clearRect(0, 0, rect.width, rect.height);
      ctx.fillStyle = "#2a2a2a";
      const bars = Math.floor(rect.width / 4);
      if (!audioUrl) {
        for (let i = 0; i < bars; i++) {
          const h = 4 + Math.sin(i * 0.4) * 3;
          ctx.fillRect(i * 4, rect.height / 2 - h / 2, 2, h);
        }
        return;
      }
      const audioContext = new AudioContext();
      const buffer = await fetch(audioUrl).then((res) => res.arrayBuffer());
      const decoded = await audioContext.decodeAudioData(buffer);
      if (cancelled) {
        audioContext.close();
        return;
      }
      const data = decoded.getChannelData(0);
      const step = Math.max(1, Math.floor(data.length / bars));
      ctx.fillStyle = "#e07845";
      for (let i = 0; i < bars; i++) {
        let sum = 0;
        for (let j = 0; j < step; j++) sum += Math.abs(data[i * step + j] || 0);
        const amp = sum / step;
        const h = Math.max(2, amp * rect.height * 2.8);
        ctx.fillRect(i * 4, rect.height / 2 - h / 2, 2, h);
      }
      audioContext.close();
    }

    draw().catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [audioUrl]);
  return ref;
}

function pageLabel(page: Page) {
  const labels: Record<Page, string> = {
    speak: "01 — speak",
    listen: "02 — listen",
    qwen: "03 — qwen studio",
    backends: "04 — backends",
    models: "05 — models",
    voices: "06 — voices",
    log: "07 — log",
    config: "08 — config",
    api: "09 — api"
  };
  return labels[page];
}

function formatTime(seconds: number) {
  if (!Number.isFinite(seconds) || seconds <= 0) return "0:00";
  const whole = Math.floor(seconds);
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

async function safeJson(res: Response): Promise<{ detail?: string }> {
  try {
    return await res.json();
  } catch {
    return {};
  }
}

async function playPreviewBlob(
  blob: Blob,
  audioRef: React.MutableRefObject<HTMLAudioElement | null>
) {
  const audio = audioRef.current;
  if (!audio) return;
  stopPreview(audio);
  const url = URL.createObjectURL(blob);
  audio.src = url;
  audio.onended = () => URL.revokeObjectURL(url);
  await audio.play();
}

function stopPreview(audio: HTMLAudioElement) {
  audio.pause();
  audio.currentTime = 0;
  if (audio.src) {
    URL.revokeObjectURL(audio.src);
    audio.removeAttribute("src");
    audio.load();
  }
}

function truncate(value: string, max: number) {
  return value.length > max ? `${value.slice(0, max - 1)}…` : value;
}

function randomBetween(min: number, max: number) {
  return min + Math.random() * (max - min);
}

function makeId() {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function patchBackend(group: ConfigGroup, name: string, patch: Partial<BackendSettings>): ConfigGroup {
  return {
    ...group,
    backends: {
      ...group.backends,
      [name]: { ...group.backends[name], ...patch }
    }
  };
}

function optionTextForConfig(config: AppConfig) {
  const result: Record<string, string> = {};
  for (const groupName of ["tts", "stt"] as const) {
    const group = config[groupName];
    for (const [name, backend] of Object.entries(group.backends)) {
      result[`${groupName}.${name}`] = JSON.stringify(backendOptions(backend), null, 2);
    }
  }
  return result;
}

function configWithOptions(config: AppConfig, optionText: Record<string, string>): AppConfig {
  return {
    ...config,
    tts: groupWithOptions("tts", config.tts, optionText),
    stt: groupWithOptions("stt", config.stt, optionText)
  };
}

function groupWithOptions(
  groupName: "tts" | "stt",
  group: ConfigGroup,
  optionText: Record<string, string>
): ConfigGroup {
  const backends: Record<string, BackendSettings> = {};
  for (const [name, backend] of Object.entries(group.backends)) {
    const raw = optionText[`${groupName}.${name}`]?.trim() || "{}";
    const options = JSON.parse(raw);
    if (!options || Array.isArray(options) || typeof options !== "object") {
      throw new Error(`${groupName}.${name} options must be a JSON object`);
    }
    backends[name] = {
      enabled: backend.enabled,
      device: backend.device,
      ttl: backend.ttl,
      ...options
    };
  }
  return { ...group, backends };
}

function backendOptions(backend: BackendSettings) {
  const { enabled: _enabled, device: _device, ttl: _ttl, ...options } = backend;
  return options;
}

export default App;
