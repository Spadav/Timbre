(function () {
  "use strict";

  const SDK = window.__HERMES_PLUGIN_SDK__;
  if (!SDK) return;

  const React = SDK.React;
  const h = React.createElement;
  const hooks = SDK.hooks || React;
  const useEffect = hooks.useEffect;
  const useState = hooks.useState;

  const API = "/api/plugins/hermes-timbre";

  async function fetchJSON(path, options) {
    return SDK.fetchJSON(API + path, options || {});
  }

  function Badge(props) {
    return h("span", { className: "timbre-dashboard__badge" }, props.children);
  }

  function Button(props) {
    return h("button", {
      className: "timbre-dashboard__button",
      type: "button",
      disabled: props.disabled,
      onClick: props.onClick,
    }, props.children);
  }

  function Select(props) {
    return h("select", {
      className: "timbre-dashboard__select",
      value: props.value || "",
      onChange: function (event) { props.onChange(event.target.value); },
    }, props.children);
  }

  function Input(props) {
    return h("input", {
      className: "timbre-dashboard__input",
      value: props.value || "",
      placeholder: props.placeholder || "",
      onChange: function (event) { props.onChange(event.target.value); },
    });
  }

  function Panel(props) {
    return h("section", { className: "timbre-dashboard__panel" },
      h("h2", { className: "timbre-dashboard__title" }, props.title),
      props.children,
    );
  }

  function backendRow(item, onAction, busyKey) {
    const key = item.kind + "/" + item.name;
    return h("div", { className: "timbre-dashboard__row", key: key },
      h("div", null,
        h("div", null, h("strong", null, item.name), " ", h(Badge, null, item.kind)),
        h("div", { className: "timbre-dashboard__muted" },
          item.enabled ? "enabled" : "disabled", " / ",
          item.loaded ? "loaded" : "unloaded", " / ",
          item.device || "default device",
        ),
      ),
      h("div", { className: "timbre-dashboard__actions" },
        h(Button, {
          disabled: busyKey === key + "/load" || item.loaded,
          onClick: function () { onAction(item, "load"); },
        }, "Load"),
        h(Button, {
          disabled: busyKey === key + "/unload" || !item.loaded,
          onClick: function () { onAction(item, "unload"); },
        }, "Unload"),
        h(Button, {
          disabled: busyKey === key + "/enable" || item.enabled,
          onClick: function () { onAction(item, "enable"); },
        }, "Enable"),
        h(Button, {
          disabled: busyKey === key + "/disable" || !item.enabled,
          onClick: function () { onAction(item, "disable"); },
        }, "Disable"),
      ),
    );
  }

  function voiceRow(item) {
    return h("div", { className: "timbre-dashboard__row", key: (item.backend || "clone") + "/" + item.name },
      h("div", null,
        h("div", null, h("strong", null, item.name), " ", h(Badge, null, item.type || "voice")),
        h("div", { className: "timbre-dashboard__muted" },
          item.backend ? "backend: " + item.backend : "cloned/custom",
          item.target ? " -> " + item.target : "",
        ),
      ),
    );
  }

  function voiceMatchesBackend(item, backend) {
    return !item.backend || item.backend === backend;
  }

  function uniqueVoiceNames(voices, backend) {
    const names = [];
    voices.forEach(function (item) {
      if (!voiceMatchesBackend(item, backend)) return;
      const name = String(item.name || "").trim();
      if (name && names.indexOf(name) === -1) names.push(name);
    });
    return names;
  }

  function VoiceCloud(props) {
    const visible = props.showAll ? props.voices : props.voices.slice(0, 18);
    if (!props.voices.length) {
      return h("p", { className: "timbre-dashboard__muted" }, "No voices returned by Timbre.");
    }
    return h("div", null,
      h("div", { className: "timbre-dashboard__voice-cloud" },
        visible.map(function (item) {
          const active = item.name === props.activeVoice;
          return h("button", {
            key: (item.backend || "clone") + "/" + item.name,
            type: "button",
            className: "timbre-dashboard__voice-chip" + (active ? " timbre-dashboard__voice-chip--active" : ""),
            onClick: function () { props.onChoose(item.name); },
            title: item.backend ? "backend: " + item.backend : "custom/cloned voice",
          }, item.name);
        }),
      ),
      props.voices.length > 18
        ? h(Button, { onClick: props.onToggle }, props.showAll ? "Show fewer" : "Show all " + props.voices.length)
        : null,
    );
  }

  function TimbreDashboard() {
    const [data, setData] = useState(null);
    const [error, setError] = useState("");
    const [busyKey, setBusyKey] = useState("");
    const [draft, setDraft] = useState(null);
    const [showAllVoices, setShowAllVoices] = useState(false);

    async function load() {
      try {
        setError("");
        const next = await fetchJSON("/summary");
        setData(next);
        setDraft({
          url: next.config && next.config.url ? next.config.url : "",
          tts_backend: next.config && next.config.tts_backend ? next.config.tts_backend : "pocket",
          stt_backend: next.config && next.config.stt_backend ? next.config.stt_backend : "parakeet",
          voice: next.config && next.config.voice ? next.config.voice : "alba",
        });
      } catch (err) {
        setError(err && err.message ? err.message : String(err));
      }
    }

    useEffect(function () { load(); }, []);

    async function onAction(item, action) {
      const key = item.kind + "/" + item.name + "/" + action;
      setBusyKey(key);
      try {
        await fetchJSON("/backends/" + item.kind + "/" + encodeURIComponent(item.name) + "/" + action, {
          method: "POST",
        });
        await load();
      } catch (err) {
        setError(err && err.message ? err.message : String(err));
      } finally {
        setBusyKey("");
      }
    }

    function updateDraft(key, value) {
      setDraft(Object.assign({}, draft || {}, { [key]: value }));
    }

    async function saveDefaults() {
      if (!draft) return;
      setBusyKey("config/save");
      try {
        const next = await fetchJSON("/config", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(draft),
        });
        setData(next);
        setDraft({
          url: next.config && next.config.url ? next.config.url : "",
          tts_backend: next.config && next.config.tts_backend ? next.config.tts_backend : "pocket",
          stt_backend: next.config && next.config.stt_backend ? next.config.stt_backend : "parakeet",
          voice: next.config && next.config.voice ? next.config.voice : "alba",
        });
        setError("");
      } catch (err) {
        setError(err && err.message ? err.message : String(err));
      } finally {
        setBusyKey("");
      }
    }

    const config = data && data.config ? data.config : {};
    const backends = data && Array.isArray(data.backends) ? data.backends : [];
    const voices = data && Array.isArray(data.voices) ? data.voices : [];
    const tts = backends.filter(function (item) { return item.kind === "tts"; });
    const stt = backends.filter(function (item) { return item.kind === "stt"; });
    const ttsNames = tts.filter(function (item) { return item.enabled; }).map(function (item) { return item.name; });
    const sttNames = stt.filter(function (item) { return item.enabled; }).map(function (item) { return item.name; });
    const activeTts = draft && draft.tts_backend ? draft.tts_backend : config.tts_backend || "pocket";
    const activeVoice = draft && draft.voice ? draft.voice : config.voice || "alba";
    const voiceNames = uniqueVoiceNames(voices, activeTts);
    const filteredVoices = voices.filter(function (item) { return voiceMatchesBackend(item, activeTts); });

    return h("div", { className: "timbre-dashboard" },
      h("div", null,
        h("h1", { className: "text-2xl font-semibold" }, "Timbre"),
        h("p", { className: "timbre-dashboard__muted" },
          "Manage the Timbre voice gateway currently configured for Hermes.",
        ),
      ),
      error ? h("div", { className: "timbre-dashboard__panel timbre-dashboard__error" }, error) : null,
      h("div", { className: "timbre-dashboard__grid" },
        h(Panel, { title: "Connection" },
          h("div", { className: "timbre-dashboard__row" },
            h("span", null, "URL"),
            h("code", null, config.url || "not configured"),
          ),
          h("div", { className: "timbre-dashboard__row" },
            h("span", null, "TTS"),
            h("code", null, (config.tts_backend || "pocket") + " / " + (config.voice || "alba")),
          ),
          h("div", { className: "timbre-dashboard__row" },
            h("span", null, "STT"),
            h("code", null, config.stt_backend || "parakeet"),
          ),
          h("div", { className: "timbre-dashboard__actions" },
            h(Button, { onClick: load }, "Refresh"),
          ),
        ),
        h(Panel, { title: "Hermes Defaults" },
          h("label", { className: "timbre-dashboard__field" },
            h("span", null, "TTS backend"),
            h(Select, {
              value: activeTts,
              onChange: function (value) { updateDraft("tts_backend", value); },
            },
              ttsNames.map(function (name) { return h("option", { key: name, value: name }, name); }),
            ),
          ),
          h("label", { className: "timbre-dashboard__field" },
            h("span", null, "STT backend"),
            h(Select, {
              value: draft && draft.stt_backend ? draft.stt_backend : config.stt_backend || "parakeet",
              onChange: function (value) { updateDraft("stt_backend", value); },
            },
              sttNames.map(function (name) { return h("option", { key: name, value: name }, name); }),
            ),
          ),
          h("label", { className: "timbre-dashboard__field" },
            h("span", null, "Voice"),
            h(Input, {
              value: activeVoice,
              placeholder: voiceNames[0] || "voice name",
              onChange: function (value) { updateDraft("voice", value); },
            }),
          ),
          h("div", { className: "timbre-dashboard__actions" },
            h(Button, { disabled: busyKey === "config/save", onClick: saveDefaults }, "Save Defaults"),
          ),
        ),
        h(Panel, { title: "Health" },
          h("div", { className: "timbre-dashboard__row" },
            h("span", null, "Status"),
            h(Badge, null, data && data.health ? data.health.status || "ok" : "unknown"),
          ),
          data && data.errors && data.errors.health
            ? h("div", { className: "timbre-dashboard__muted" }, data.errors.health)
            : null,
        ),
      ),
      h(Panel, { title: "TTS Backends" },
        tts.length ? tts.map(function (item) { return backendRow(item, onAction, busyKey); })
          : h("p", { className: "timbre-dashboard__muted" }, "No TTS backends returned by Timbre."),
      ),
      h(Panel, { title: "STT Backends" },
        stt.length ? stt.map(function (item) { return backendRow(item, onAction, busyKey); })
          : h("p", { className: "timbre-dashboard__muted" }, "No STT backends returned by Timbre."),
      ),
      h(Panel, { title: "Voices" },
        h("p", { className: "timbre-dashboard__muted" },
          "Showing voices for ", h("strong", null, activeTts), ". Click a voice to set the Hermes default.",
        ),
        h(VoiceCloud, {
          voices: filteredVoices,
          activeVoice: activeVoice,
          showAll: showAllVoices,
          onChoose: function (name) { updateDraft("voice", name); },
          onToggle: function () { setShowAllVoices(!showAllVoices); },
        }),
      ),
    );
  }

  window.__HERMES_PLUGINS__.register("hermes-timbre", TimbreDashboard);
})();
