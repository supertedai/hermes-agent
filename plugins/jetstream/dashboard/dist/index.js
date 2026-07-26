/**
 * Jetstream Env — Dashboard Plugin (NATIVE rebuild).
 *
 * Bygget med Nous DS-komponentene fra plugin-SDK-en (Card/CardHeader/CardTitle/
 * CardContent/Badge/Button/Input/Select) + Hermes' egne tailwind-klasser — samme
 * komponentbibliotek som Keys/Skills/Plugins/Funn-sidene. Ingen håndrullet CSS
 * (style.css er tom med vilje).
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
  const { Card, CardHeader, CardTitle, CardContent, Badge, Button, Input, Select, SelectOption } = SDK.components;
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

  const GRID = { display: "grid", gap: "0.5rem", gridTemplateColumns: "repeat(auto-fill, minmax(155px, 1fr))" };
  const TD = "py-1.5 pr-3 align-top";

  // Native seksjon = DS Card + header (tittel + valgfri teller-badge) + content.
  // Plain helper (kalles direkte, IKKE via h()) — React gir funksjonskomponenter
  // kun props, så children må sendes som eksplisitt arg her.
  function Section(opts, content) {
    return h(Card, { className: "rounded-none" },
      h(CardHeader, { className: "py-3 px-4" },
        h("div", { className: "flex items-center justify-between gap-2" },
          h(CardTitle, { className: "text-sm" }, opts.title),
          opts.badge != null ? h(Badge, { tone: "secondary", className: "text-xs" }, String(opts.badge)) : null),
        opts.sub ? h("p", { className: "text-xs text-muted-foreground mt-1" }, opts.sub) : null),
      h(CardContent, { className: "px-4 pb-4" }, content));
  }

  function Table(cols, body) {
    return h("div", { className: "overflow-x-auto" },
      h("table", { className: "w-full text-sm" },
        h("thead", null, h("tr", { className: "border-b border-border" },
          cols.map((c) => h("th", { key: c,
            className: "text-left font-medium text-[0.6875rem] uppercase tracking-wider text-muted-foreground py-2 pr-3" }, c)))),
        h("tbody", null, body)));
  }

  // The SDK's Select fires onValueChange(value); older code calls
  // onChange({target:{value}}). Wire both so a setter works with either API.
  function selectChangeHandler(setter) {
    return {
      onValueChange: (v) => setter(v == null ? "" : v),
      onChange: (e) => { const v = e && e.target ? e.target.value : e; setter(v == null ? "" : v); },
    };
  }

  // Migrasjons-toner — kun DS-gyldige (secondary/success/destructive/outline).
  const MIG = {
    proposed:      { label: "foreslått",     tone: "secondary" },
    legacy_daemon: { label: "legacy-daemon", tone: "outline" },
    shadow:        { label: "shadow",        tone: "secondary" },
    active:        { label: "aktiv",         tone: "success" },
    throttled:     { label: "strupet (D4)",  tone: "destructive" },
    retired:       { label: "pensjonert",    tone: "outline" },
  };

  function ActionBar({ s, refresh, setMsg }) {
    const [consumer, setConsumer] = useState("");
    const post = useCallback((path, body, okMsg) => {
      jfetch(path, { method: "POST", headers: { "Content-Type": "application/json" },
                     body: JSON.stringify(body) })
        .then(() => { setMsg(okMsg); refresh(); })
        .catch((e) => setMsg("feil: " + e));
    }, [refresh, setMsg]);
    return h("div", { className: "flex flex-wrap items-center gap-2 pt-2" },
      h(Input, { className: "h-8 text-sm w-48", placeholder: "konsument…",
                 value: consumer, onChange: (e) => setConsumer(e.target.value),
                 onClick: (e) => e.stopPropagation() }),
      h(Button, { size: "sm", outlined: true, disabled: !consumer,
                  onClick: (e) => { e.stopPropagation();
                    post("/consumer", { source: s.name, consumer },
                         "konsument '" + consumer + "' deklarert for " + s.name); } },
        "deklarer konsument"),
      (s.migration !== "shadow" && s.migration !== "retired")
        ? h(Button, { size: "sm", outlined: true,
                      onClick: (e) => { e.stopPropagation();
                        post("/migration", { source: s.name, status: "shadow" }, s.name + " → shadow"); } },
            "→ shadow")
        : null,
      (s.migration !== "retired" && s.migration !== "legacy_daemon")
        ? h(Button, { size: "sm", variant: "destructive",
                      onClick: (e) => { e.stopPropagation();
                        post("/migration", { source: s.name, status: "retired" }, s.name + " pensjonert (soft)"); } },
            "pensjoner")
        : null);
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
    return Section({ title: "＋ legg til kilde",
        sub: "Nye kilder lander som 'proposed' (propose-first). Konsument + shadow-flipp er egne steg — D4 håndheves server-side." },
      h("div", { className: "flex flex-wrap items-center gap-2" },
        h(Input, { className: "h-8 text-sm w-48", placeholder: "navn (kebab-case)",
                   value: f.name, onChange: upd("name") }),
        h(Select, Object.assign({ value: f.source_kind, className: "h-8 text-sm w-40" },
                                 selectChangeHandler((v) => setF({ ...f, source_kind: v }))),
          ["rss", "api_poller", "paper_api", "web_fetch", "crawler", "repo_sync"].map((k) =>
            h(SelectOption, { key: k, value: k }, k))),
        h(Input, { className: "h-8 text-sm w-36", placeholder: "domene",
                   value: f.domain, onChange: upd("domain") }),
        h(Input, { className: "h-8 text-sm flex-1 min-w-[16rem]", placeholder: "endepunkt-URL (https://…)",
                   value: f.endpoint_hint, onChange: upd("endpoint_hint") }),
        h(Input, { className: "h-8 text-sm w-32", placeholder: "kadens (min)",
                   value: f.cadence_minutes, onChange: upd("cadence_minutes") }),
        h(Input, { className: "h-8 text-sm w-40", placeholder: "parser (valgfri)",
                   value: f.parser, onChange: upd("parser") }),
        h(Button, { size: "sm", outlined: true, disabled: !f.name, onClick: submit }, "foreslå kilde")));
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
    const rows = names.map((n) => {
      const st = fpByName[n]; const rf = refByName[n];
      return h("tr", { key: n, className: "border-t border-border/60" },
        h("td", { className: TD + " font-medium font-mono text-xs" }, n),
        h("td", { className: TD }, st
          ? h("span", { className: "text-xs font-mono text-muted-foreground" }, st.fingerprint + " · " + st.mtime)
          : h(Badge, { tone: "destructive", className: "text-xs" }, "mangler ⚠")),
        h("td", { className: TD + " text-muted-foreground" }, rf ? String(rf.sources) + " kilder" : "—"),
        h("td", { className: TD + " text-muted-foreground font-mono text-xs" }, rf ? (rf.brukt_av || []).join(", ") : ""));
    });
    return Section({ title: "nøkler",
        sub: "verdier bor KUN i .11-storen — kanalen er write-only (get nektes); her vises navn/fingeravtrykk" },
      h("div", { className: "flex flex-col gap-3" },
        Table(["nøkkelnavn", "i store (.11)", "brukes av", "kilder"], rows),
        h("div", { className: "flex flex-wrap items-center gap-2 pt-3 border-t border-border/60" },
          h(Input, { className: "h-8 text-sm w-48", placeholder: "NØKKELNAVN", value: kn,
                     onChange: (e) => setKn(e.target.value.toUpperCase()) }),
          h(Input, { className: "h-8 text-sm flex-1 min-w-[16rem]", type: "password",
                     placeholder: "verdi (write-only — vises aldri igjen)",
                     value: kv, onChange: (e) => setKv(e.target.value) }),
          h(Button, { size: "sm", outlined: true, disabled: !kn || !kv, onClick: setKey },
            "sett / rotér nøkkel"))));
  }

  function SourceRows({ s, refresh, setMsg, expanded, onToggle }) {
    const mig = MIG[s.migration] || { label: s.migration || "?", tone: "outline" };
    const endpoint = s.endpoint || "—";
    const endpointShort = endpoint.length > 48 ? endpoint.slice(0, 45) + "…" : endpoint;
    const rows = [
      h("tr", { key: s.name + "-r", className: "border-t border-border/60 cursor-pointer hover:bg-muted/20",
                onClick: onToggle },
        h("td", { className: TD + " font-medium" }, s.name),
        h("td", { className: TD + " text-muted-foreground" }, s.kind || ""),
        h("td", { className: TD }, h(Badge, { tone: mig.tone, className: "text-xs" }, mig.label)),
        h("td", { className: TD }, s.consumers > 0
          ? h(Badge, { tone: "success", className: "text-xs" },
              "✓ " + s.consumers + " konsument" + (s.consumers > 1 ? "er" : ""))
          : h(Badge, { tone: "destructive", className: "text-xs" }, "ingen ⚠ (D4)")),
        h("td", { className: TD + " text-muted-foreground font-mono text-xs", title: endpoint }, endpointShort),
        h("td", { className: TD + " text-muted-foreground font-mono text-xs" }, (s.nokkelref || []).join(", ") || "—")),
    ];
    if (expanded) {
      rows.push(h("tr", { key: s.name + "-x", className: "border-t border-border/60 bg-background/40" },
        h("td", { colSpan: 6, className: "p-3" },
          h("div", { className: "text-xs text-muted-foreground flex flex-wrap gap-x-3 gap-y-1" },
            s.container ? h("span", null, "legacy-container: " + s.container) : null,
            h("span", null, "konsum-status: " + (s.consumer_status || "?")),
            s.updated ? h("span", null, "oppdatert: " + s.updated) : null),
          h(ActionBar, { s, refresh, setMsg }))));
    }
    return rows;
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

    const undeclared = (data && data.sources ? data.sources : [])
      .filter((s) => !(s.consumers > 0)).length;

    const stats = [
      { n: sum ? (sum.total || 0) : "…", label: "kilder" },
      { n: sum ? ((sum.by_migration || {}).shadow || 0) : "…", label: "i shadow" },
      { n: sum ? ((sum.by_migration || {}).legacy_daemon || 0) : "…", label: "legacy igjen" },
      { n: undeclared, label: "uten konsument", warn: undeclared > 0 },
    ];

    if (err) {
      return h("div", { className: "flex flex-col gap-4 p-4" },
        Section({ title: "Env — Jetstream: verden → Symbiose" },
          h("p", { className: "text-sm text-destructive" }, "Feil: " + err)));
    }

    return h("div", { className: "flex flex-col gap-4 p-4" },
      h("p", { className: "text-sm text-muted-foreground max-w-3xl" },
        "Den kanoniske flaten for eksterne kilder og nøkler. Alt legges inn og leses her — agenter og "
        + "workers leser samme register (grafen), skriver via samme gate. Nye kilder lander som 'proposed'; "
        + "shadow krever en levende konsument (D4). Nøkkelverdier bor kun i .11-storen (write-only)."),
      msg ? h("div", { className: "border border-border bg-background/40 px-3 py-2 text-sm cursor-pointer",
                       onClick: () => setMsg(null) }, msg) : null,
      h("div", { style: GRID },
        stats.map((s) => h("div", { key: s.label, className: "border border-border bg-background/40 px-3 py-2" },
          h("div", { className: "text-2xl font-semibold tabular-nums leading-none" + (s.warn ? " text-destructive" : "") },
            String(s.n)),
          h("div", { className: "text-[0.6875rem] uppercase tracking-wide text-muted-foreground mt-1 break-words" },
            s.label)))),
      h(AddSourceForm, { refresh, setMsg }),
      h(KeysPanel, { setMsg }),
      Object.keys(byDomain).sort().map((d) =>
        h("div", { key: d },
          Section({ title: d, badge: byDomain[d].length },
            Table(["kilde", "type", "status", "konsum-kontrakt", "endepunkt", "nøkler"],
              byDomain[d].flatMap((s) =>
                SourceRows({ s, refresh, setMsg,
                             expanded: expanded === s.name,
                             onToggle: () => setExpanded(expanded === s.name ? null : s.name) })))))),
      !data ? h("p", { className: "text-sm text-muted-foreground" }, "laster registeret…") : null);
  }

  if (window.__HERMES_PLUGINS__ && typeof window.__HERMES_PLUGINS__.register === "function") {
    window.__HERMES_PLUGINS__.register("jetstream", JetstreamEnvView);
  }
})();
