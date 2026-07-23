/**
 * Jetstream Env — Dashboard Plugin v0.2 (BL-2348/BL-2354)
 *
 * DEN kanoniske flaten (:9119/env) for verden→Symbiose-ingest: alle agenter,
 * workers og Morten legger inn og leser kilder (API/RSS/…) og nøkler HER.
 *
 * Sikkerhetsmodell: GUI-en er creds-fri. Lesing = faste Cypher via unified-API
 * (read-only). Skriving = proxy til unified-APIets validerte skriveport på .12
 * (D4 håndhevet server-side: shadow krever levende konsument; active avvises
 * til Fase 3; nye kilder lander som 'proposed'). Nøkler = write-only-kanal til
 * .11-storen (forced-command: set/list tillatt, get NEKTES — verdier kan gå
 * inn, aldri ut; kun fingeravtrykk vises).
 */
(function () {
  "use strict";

  const SDK = window.__HERMES_PLUGIN_SDK__;
  if (!SDK) return;

  const { React } = SDK;
  const h = React.createElement;
  const { Card, CardContent, Badge } = SDK.components;
  const { useState, useEffect, useMemo, useCallback } = SDK.hooks;

  const API = "/api/plugins/jetstream";
  const jfetch = (path, opts) =>
    SDK.fetchJSON ? SDK.fetchJSON(API + path, opts)
      : SDK.authedFetch ? SDK.authedFetch(API + path, opts).then((r) => r.json())
      : fetch(API + path, opts).then((r) => r.json());

  function useData(path, tick) {
    const [data, setData] = useState(null);
    const [err, setErr] = useState(null);
    useEffect(() => {
      let alive = true;
      jfetch(path).then((d) => { if (alive) { setData(d); setErr(null); } })
        .catch((e) => alive && setErr(String(e)));
      return () => { alive = false; };
    }, [path, tick]);
    return { data, err };
  }

  const MIG = {
    proposed: { label: "foreslått", cls: "js-badge-proposed" },
    legacy_daemon: { label: "legacy-daemon", cls: "js-badge-legacy" },
    shadow: { label: "shadow", cls: "js-badge-shadow" },
    active: { label: "aktiv", cls: "js-badge-live" },
    throttled: { label: "strupet (D4)", cls: "js-badge-warn" },
    retired: { label: "pensjonert", cls: "js-badge-retired" },
  };

  function ActionBar({ s, refresh, setMsg }) {
    const [consumer, setConsumer] = useState("");
    const post = useCallback((path, body, okMsg) => {
      jfetch(path, { method: "POST", headers: { "Content-Type": "application/json" },
                     body: JSON.stringify(body) })
        .then(() => { setMsg(okMsg); refresh(); })
        .catch((e) => setMsg("feil: " + e));
    }, [refresh, setMsg]);
    return h("div", { className: "js-actions" },
      h("input", { className: "js-inline-input", placeholder: "konsument…",
                   value: consumer, onChange: (e) => setConsumer(e.target.value),
                   onClick: (e) => e.stopPropagation() }),
      h("button", { className: "js-btn", disabled: !consumer,
                    onClick: (e) => { e.stopPropagation();
                      post("/consumer", { source: s.name, consumer },
                           "konsument '" + consumer + "' deklarert for " + s.name); } },
        "deklarer konsument"),
      s.migration !== "shadow" && s.migration !== "retired" &&
        h("button", { className: "js-btn js-btn-go",
                      onClick: (e) => { e.stopPropagation();
                        post("/migration", { source: s.name, status: "shadow" },
                             s.name + " → shadow"); } }, "→ shadow"),
      s.migration !== "retired" && s.migration !== "legacy_daemon" &&
        h("button", { className: "js-btn js-btn-danger",
                      onClick: (e) => { e.stopPropagation();
                        post("/migration", { source: s.name, status: "retired" },
                             s.name + " pensjonert (soft)"); } }, "pensjoner"));
  }

  function AddSourceForm({ refresh, setMsg }) {
    const [f, setF] = useState({ name: "", source_kind: "rss", domain: "general",
                                 endpoint_hint: "", cadence_minutes: "60", parser: "" });
    const upd = (k) => (e) => setF({ ...f, [k]: e.target.value });
    const submit = () => {
      const body = { name: f.name, source_kind: f.source_kind, domain: f.domain,
                     endpoint_hint: f.endpoint_hint || null,
                     cadence_minutes: parseInt(f.cadence_minutes, 10) || 60,
                     parser: f.parser || null, nokkelref: [] };
      jfetch("/sources", { method: "POST", headers: { "Content-Type": "application/json" },
                           body: JSON.stringify(body) })
        .then(() => { setMsg("kilde '" + f.name + "' lagret som 'proposed' — deklarer konsument før shadow (D4)");
                      setF({ ...f, name: "", endpoint_hint: "" }); refresh(); })
        .catch((e) => setMsg("feil: " + e));
    };
    return h(Card, null, h(CardContent, { className: "js-form" },
      h("h3", { className: "js-form-title" }, "＋ legg til kilde"),
      h("div", { className: "js-form-grid" },
        h("input", { className: "js-inline-input", placeholder: "navn (kebab-case)",
                     value: f.name, onChange: upd("name") }),
        h("select", { className: "js-inline-input", value: f.source_kind, onChange: upd("source_kind") },
          ["rss", "api_poller", "paper_api", "web_fetch", "crawler", "repo_sync"].map((k) =>
            h("option", { key: k, value: k }, k))),
        h("input", { className: "js-inline-input", placeholder: "domene",
                     value: f.domain, onChange: upd("domain") }),
        h("input", { className: "js-inline-input js-wide", placeholder: "endepunkt-URL (https://…)",
                     value: f.endpoint_hint, onChange: upd("endpoint_hint") }),
        h("input", { className: "js-inline-input", placeholder: "kadens (min)",
                     value: f.cadence_minutes, onChange: upd("cadence_minutes") }),
        h("input", { className: "js-inline-input", placeholder: "parser (valgfri)",
                     value: f.parser, onChange: upd("parser") }),
        h("button", { className: "js-btn js-btn-go", disabled: !f.name, onClick: submit },
          "foreslå kilde")),
      h("p", { className: "js-hint" },
        "Nye kilder lander som 'proposed' (propose-first). Konsument + shadow-flipp er egne steg — D4 håndheves server-side.")));
  }

  function KeysPanel({ setMsg }) {
    const [tick, setTick] = useState(0);
    const { data: refs } = useData("/keys", tick);
    const { data: store } = useData("/keystore", tick);
    const [kn, setKn] = useState("");
    const [kv, setKv] = useState("");
    const fpByName = useMemo(() => {
      const m = {};
      ((store && store.keys) || []).forEach((k) => { m[k.name] = k; });
      return m;
    }, [store]);
    const refByName = useMemo(() => {
      const m = {};
      ((refs && refs.keys) || []).forEach((k) => { m[k.name] = k; });
      return m;
    }, [refs]);
    const names = useMemo(() => {
      const s = new Set(Object.keys(refByName));
      Object.keys(fpByName).forEach((n) => s.add(n));
      return Array.from(s).sort();
    }, [refByName, fpByName]);
    const setKey = () => {
      jfetch("/keys/" + kn, { method: "PUT", headers: { "Content-Type": "application/json" },
                              body: JSON.stringify({ value: kv }) })
        .then((r) => { setMsg("nøkkel satt: " + (r.detail || kn)); setKv(""); setKn("");
                       setTick((t) => t + 1); })
        .catch((e) => setMsg("feil: " + e));
    };
    return h("div", { className: "js-domain" },
      h("h3", { className: "js-domain-title" }, "nøkler ",
        h("span", { className: "js-domain-count" },
          "verdier bor KUN i .11-storen — kanalen er write-only (get nektes); her vises navn/fingeravtrykk")),
      h("table", { className: "js-table" },
        h("thead", null, h("tr", null,
          ["nøkkelnavn", "i store (.11)", "brukes av", "kilder"].map((c) => h("th", { key: c }, c)))),
        h("tbody", null, names.map((n) => {
          const st = fpByName[n]; const rf = refByName[n];
          return h("tr", { key: n, className: "js-row" },
            h("td", { className: "js-name" }, n),
            h("td", null, st
              ? h("span", { className: "js-consumer-ok" }, st.fingerprint + " · " + st.mtime)
              : h("span", { className: "js-consumer-missing" }, "mangler ⚠")),
            h("td", null, rf ? String(rf.sources) + " kilder" : "—"),
            h("td", { className: "js-container" }, rf ? (rf.brukt_av || []).join(", ") : ""));
        }))),
      h("div", { className: "js-keyform" },
        h("input", { className: "js-inline-input", placeholder: "NØKKELNAVN", value: kn,
                     onChange: (e) => setKn(e.target.value.toUpperCase()) }),
        h("input", { className: "js-inline-input js-wide",
                     placeholder: "verdi (write-only — vises aldri igjen)",
                     type: "password", value: kv, onChange: (e) => setKv(e.target.value) }),
        h("button", { className: "js-btn js-btn-go", disabled: !kn || !kv, onClick: setKey },
          "sett / rotér nøkkel")));
  }

  function JetstreamEnvView() {
    const [tick, setTick] = useState(0);
    const [msg, setMsg] = useState(null);
    const [expanded, setExpanded] = useState(null);
    const refresh = useCallback(() => setTick((t) => t + 1), []);
    const { data: sum } = useData("/summary", tick);
    const { data, err } = useData("/sources", tick);

    useEffect(() => {
      const t = setInterval(refresh, 60000);
      return () => clearInterval(t);
    }, [refresh]);

    const byDomain = useMemo(() => {
      const out = {};
      (data && data.sources ? data.sources : []).forEach((s) => {
        (out[s.domain || "general"] = out[s.domain || "general"] || []).push(s);
      });
      return out;
    }, [data]);

    if (err) return h("div", { className: "js-wrap" },
      h(Card, null, h(CardContent, null, "Feil: " + err)));
    const undeclared = (data && data.sources ? data.sources : [])
      .filter((s) => !(s.consumers > 0)).length;

    return h("div", { className: "js-wrap" },
      h("div", { className: "js-header" },
        h("h2", null, "Env — Jetstream: verden → Symbiose"),
        h("p", { className: "js-sub" },
          "Den kanoniske flaten for eksterne kilder og nøkler. Alt legges inn og leses her — agenter og workers leser samme register (grafen), skriver via samme gate.")),
      msg && h("div", { className: "js-msg", onClick: () => setMsg(null) }, msg),
      sum && h("div", { className: "js-stats" },
        [["kilder", (sum.total || 0), ""],
         ["i shadow", ((sum.by_migration || {}).shadow || 0), ""],
         ["legacy igjen", ((sum.by_migration || {}).legacy_daemon || 0), ""],
         ["uten konsument", undeclared, "js-stat-warn"]].map((t) =>
          h(Card, { key: t[0] }, h(CardContent, { className: "js-stat " + t[2] },
            h("div", { className: "js-stat-n" }, String(t[1])),
            h("div", { className: "js-stat-l" }, t[0]))))),
      h(AddSourceForm, { refresh, setMsg }),
      h(KeysPanel, { setMsg }),
      Object.keys(byDomain).sort().map((d) =>
        h("div", { key: d, className: "js-domain" },
          h("h3", { className: "js-domain-title" }, d, " ",
            h("span", { className: "js-domain-count" }, "(" + byDomain[d].length + ")")),
          h("table", { className: "js-table" },
            h("thead", null, h("tr", null,
              ["kilde", "type", "status", "konsum-kontrakt", "endepunkt", "nøkler"].map((c) =>
                h("th", { key: c }, c)))),
            h("tbody", null, byDomain[d].flatMap((s) =>
              SourceRow({ s, refresh, setMsg,
                          expanded: expanded === s.name,
                          onToggle: () => setExpanded(expanded === s.name ? null : s.name) })))))),
      !data && h("div", { className: "js-loading" }, "laster registeret…"));
  }

  if (window.__HERMES_PLUGINS__ && typeof window.__HERMES_PLUGINS__.register === "function") {
    window.__HERMES_PLUGINS__.register("jetstream", JetstreamEnvView);
  }
})();
