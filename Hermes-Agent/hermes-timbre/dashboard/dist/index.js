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
    const response = await fetch(API + path, options || {});
    const text = await response.text();
    let payload = {};
    if (text) {
      try { payload = JSON.parse(text); }
      catch (_err) { payload = { detail: text }; }
    }
    if (!response.ok) {
      throw new Error(payload.detail || response.statusText || "Request failed");
    }
    return payload;
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

  function TimbreDashboard() {
    const [data, setData] = useState(null);
    const [error, setError] = useState("");
    const [busyKey, setBusyKey] = useState("");

    async function load() {
      try {
        setError("");
        setData(await fetchJSON("/summary"));
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

    const config = data && data.config ? data.config : {};
    const backends = data && Array.isArray(data.backends) ? data.backends : [];
    const voices = data && Array.isArray(data.voices) ? data.voices : [];
    const tts = backends.filter(function (item) { return item.kind === "tts"; });
    const stt = backends.filter(function (item) { return item.kind === "stt"; });

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
        voices.length ? voices.slice(0, 80).map(voiceRow)
          : h("p", { className: "timbre-dashboard__muted" }, "No voices returned by Timbre."),
      ),
    );
  }

  window.__HERMES_PLUGINS__.register("hermes-timbre", TimbreDashboard);
})();
