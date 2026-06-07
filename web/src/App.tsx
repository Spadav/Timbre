import {
  Headphones,
  Mic,
  Play,
  Radio,
  RefreshCw,
  Settings,
  Square,
  Trash2,
  Upload,
  Volume2
} from "lucide-react";
import { ChangeEvent, FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

type Page = "speak" | "listen" | "backends" | "voices" | "config";

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
  type: "preset" | "cloned";
  audio_path?: string | null;
  prepared_backends?: string[];
};

type Health = {
  status: string;
  service: string;
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
  }
};

function App() {
  const [page, setPage] = useState<Page>("speak");
  const [online, setOnline] = useState(false);
  const [backends, setBackends] = useState<Backend[]>([]);
  const [voices, setVoices] = useState<Voice[]>([]);
  const [statusText, setStatusText] = useState("starting");

  const refresh = useCallback(async () => {
    try {
      const [health, backendList, voiceList] = await Promise.all([
        api.health(),
        api.backends(),
        api.voices()
      ]);
      setOnline(health.status === "ok");
      setBackends(backendList);
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
          <NavItem page="backends" active={page} onClick={setPage} label="Backends" icon={<Radio />} />
          <NavItem page="voices" active={page} onClick={setPage} label="Voices" icon={<Mic />} />
          <NavItem page="config" active={page} onClick={setPage} label="Config" icon={<Settings />} />
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
            <SpeakPage backends={backends} voices={voices} onRefresh={refresh} />
          )}
          {page === "listen" && <ListenPage backends={backends} />}
          {page === "backends" && <BackendsPage backends={backends} />}
          {page === "voices" && <VoicesPage voices={voices} onRefresh={refresh} />}
          {page === "config" && <ConfigPage backends={backends} />}
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
  onRefresh
}: {
  backends: Backend[];
  voices: Voice[];
  onRefresh: () => void;
}) {
  const ttsBackends = backends.filter((backend) => backend.kind === "tts");
  const [text, setText] = useState("Hello, this is Timbre speaking through a local voice gateway.");
  const [backend, setBackend] = useState("pocket");
  const [voice, setVoice] = useState("aria");
  const [format, setFormat] = useState("wav");
  const [speed, setSpeed] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [audioUrl, setAudioUrl] = useState("");
  const [duration, setDuration] = useState(0);
  const [generationSeconds, setGenerationSeconds] = useState(0);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const waveformRef = useWaveform(audioUrl);

  const voiceOptions = useMemo(() => {
    const cloned = voices.filter(
      (item) => item.type === "cloned" && item.prepared_backends?.includes(backend)
    );
    const presets = voices.filter((item) => item.type === "preset" && item.backend === backend);
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
      setGenerationSeconds((performance.now() - start) / 1000);
      onRefresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "generation failed");
    } finally {
      setBusy(false);
    }
  }

  const rtf = duration > 0 && generationSeconds > 0 ? generationSeconds / duration : 0;

  return (
    <div className="page-grid">
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
          <button className="play-btn" onClick={() => audioRef.current?.play()} disabled={!audioUrl} title="Play">
            <Play size={15} />
          </button>
          <div className="track" />
          <div className="wave-time">
            {formatTime(audioRef.current?.currentTime || 0)} / {formatTime(duration)}
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
  );
}

function ListenPage({ backends }: { backends: Backend[] }) {
  const sttBackends = backends.filter((backend) => backend.kind === "stt");
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
      setProcessingSeconds((performance.now() - start) / 1000);
    } catch (err) {
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
          <button className="play-btn" onClick={() => audioRef.current?.play()} disabled={!audioUrl} title="Play">
            <Play size={15} />
          </button>
          <div className="track" />
          <div className="wave-time">0:00 / {formatTime(duration)}</div>
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

function BackendsPage({ backends }: { backends: Backend[] }) {
  const tts = backends.filter((item) => item.kind === "tts");
  const stt = backends.filter((item) => item.kind === "stt");
  return (
    <div className="page-grid">
      <div className="stats-row">
        <Metric label="tts" value={String(tts.length)} />
        <Metric label="stt" value={String(stt.length)} />
        <Metric label="total" value={String(backends.length)} />
        <Metric label="loaded" value={String(backends.filter((item) => item.loaded).length)} />
      </div>
      <BackendGroup title="text to speech" backends={tts} />
      <BackendGroup title="speech to text" backends={stt} />
    </div>
  );
}

function VoicesPage({ voices, onRefresh }: { voices: Voice[]; onRefresh: () => void }) {
  const [name, setName] = useState("");
  const [backend, setBackend] = useState("pocket");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const cloned = voices.filter((voice) => voice.type === "cloned");
  const presets = voices.filter((voice) => voice.type === "preset");

  async function upload(event: FormEvent) {
    event.preventDefault();
    if (!file || !name.trim()) return;
    setBusy(true);
    setError("");
    const form = new FormData();
    form.append("name", name.trim());
    form.append("backend", backend);
    form.append("precompute", "true");
    form.append("file", file);
    try {
      const res = await fetch("/v1/voices", { method: "POST", body: form });
      if (!res.ok) {
        const body = await safeJson(res);
        throw new Error(body.detail || `upload failed: ${res.status}`);
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
        <button className="primary-btn" disabled={busy || !name || !file}>
          {busy ? "Processing" : "Create"}
        </button>
      </form>
      {error && <div className="error-line">{error}</div>}

      <SectionHeader num="02" title="cloned" right={`${cloned.length}`} />
      <div className="voice-grid">
        {cloned.map((voice) => (
          <div className="voice-card" key={voice.name}>
            <div className="voice-name">{voice.name}</div>
            <div className="voice-meta">{voice.prepared_backends?.join(", ") || "reference only"}</div>
            <button className="small-btn danger" onClick={() => remove(voice.name)}>
              <Trash2 size={13} />
              Delete
            </button>
          </div>
        ))}
      </div>

      <SectionHeader num="03" title="presets" right={`${presets.length}`} />
      <div className="voice-grid">
        {presets.map((voice) => (
          <div className="voice-card" key={`${voice.backend}-${voice.name}`}>
            <div className="voice-name">{voice.name}</div>
            <div className="voice-meta">{voice.backend} · built-in</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ConfigPage({ backends }: { backends: Backend[] }) {
  return (
    <div className="page-grid">
      <SectionHeader num="01" title="runtime" />
      <div className="config-box">
        <div>API: same-origin</div>
        <div>UI: Vite React TypeScript</div>
        <div>Backends: {backends.map((item) => item.name).join(", ") || "none"}</div>
        <div>Config: ~/.config/timbre/config.yaml</div>
      </div>
    </div>
  );
}

function BackendGroup({ title, backends }: { title: string; backends: Backend[] }) {
  return (
    <div>
      <SectionHeader num={title.startsWith("text") ? "01" : "02"} title={title} />
      <div className="backend-list">
        {backends.map((backend) => (
          <div className="backend-card" key={backend.name}>
            <div>
              <div className="backend-title">{backend.name}</div>
              <div className="backend-meta">
                {backend.device} · TTL: {backend.ttl === 0 ? "keep warm" : `${backend.ttl}s`}
              </div>
            </div>
            <div className={backend.loaded ? "backend-state loaded" : "backend-state idle"}>
              <span className={backend.loaded ? "dot-g" : "dot-r"} />
              {backend.loaded ? "loaded" : "idle"}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function SectionHeader({ num, title, right }: { num: string; title: string; right?: string }) {
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

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value}</div>
    </div>
  );
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
    backends: "03 — backends",
    voices: "04 — voices",
    config: "05 — config"
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

export default App;
