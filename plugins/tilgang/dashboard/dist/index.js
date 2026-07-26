/**
 * Tilgang — access-kartet + creds-lager (BL-2378). NATIVE: bygget med Nous
 * DS-komponentene fra plugin-SDK-en (Card/CardHeader/CardTitle/CardContent/
 * Badge/Button) + Hermes' egne tailwind-klasser — samme komponentbibliotek som
 * Keys/Skills/Plugins-sidene. Ingen håndrullet CSS (style.css er tom med vilje).
 *
 * Ett brett for hvordan Symbiosen henger sammen: hvem når hva (SSH/tunnel/sudo),
 * formål, status — og et write-only creds-lager (verdier bor kun i .11-storen;
 * her vises navn + fingeravtrykk, aldri hemmeligheter).
 */
(function () {
  "use strict";

  const SDK = window.__HERMES_PLUGIN_SDK__;
  if (!SDK) return;
  const { React } = SDK;
  const h = React.createElement;
  const { Card, CardHeader, CardTitle, CardContent, Badge, Button } = SDK.components;
  const { useState, useEffect, useMemo } = SDK.hooks;

  const API = "/api/plugins/tilgang";
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
  const INPUT = "border border-border bg-background/40 px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground";

  // Badge-toner — kun DS-gyldige (secondary/success/destructive/outline)
  const routeTone = (s) => s === "aktiv" ? "success"
    : s === "mangler" ? "destructive"
    : s === "inaktiv" ? "secondary" : "outline";

  // Native seksjon = DS Card + header (tittel + valgfri badge) + content.
  // Plain helper (kalles direkte, IKKE via h()) — React gir funksjonskomponenter
  // kun props, så children må sendes som eksplisitt arg her.
  function Section(opts, content) {
    return h(Card, { className: "rounded-none" },
      h(CardHeader, { className: "py-3 px-4" },
        h("div", { className: "flex items-center justify-between gap-2" },
          h(CardTitle, { className: "text-sm" }, opts.title),
          opts.badge != null ? h(Badge, { tone: opts.badgeTone || "secondary", className: "text-xs" }, String(opts.badge)) : null),
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

  function tile(value, label) {
    return h("div", { key: label, className: "border border-border bg-background/40 px-3 py-2" },
      h("div", { className: "text-2xl font-semibold tabular-nums leading-none" }, value),
      h("div", { className: "text-[0.6875rem] uppercase tracking-wide text-muted-foreground mt-1 break-words" }, label));
  }

  function Matrix() {
    const { data, err } = useData("/routes", 0);
    const rows = (data && data.routes) || [];
    return Section({ title: "Tilgangskart", badge: rows.length, sub: "hvem når hva, og hvorfor" },
      err ? h("p", { className: "text-sm text-destructive" }, "kart utilgjengelig: " + err)
        : Table(["fra", "til", "metode", "identitet", "formål", "status"],
            rows.map((r, i) =>
              h("tr", { key: i, className: "border-t border-border/60" },
                h("td", { className: TD + " font-medium whitespace-nowrap" }, r.from_host),
                h("td", { className: TD + " font-medium whitespace-nowrap" }, r.to_host),
                h("td", { className: TD }, r.method),
                h("td", { className: TD + " font-mono text-xs text-muted-foreground" }, r.credential || ""),
                h("td", { className: TD + " text-muted-foreground" }, r.purpose || ""),
                h("td", { className: TD }, h(Badge, { tone: routeTone(r.status), className: "text-xs" }, r.status || "?"))))));
  }

  function CredStore(props) {
    const routes = (props && props.routes) || [];
    const [tick, setTick] = useState(0);
    const { data } = useData("/store", tick);
    const [name, setName] = useState("");
    const [val, setVal] = useState("");
    const [msg, setMsg] = useState(null);
    const have = useMemo(() => {
      const m = {};
      ((data && data.keys) || []).forEach((k) => { m[k.name] = k; });
      return m;
    }, [data]);
    // slots kartet etterspør (store_slot på :AccessRoute), + det som alt fins
    const slots = useMemo(() => {
      const s = new Set();
      routes.forEach((r) => { if (r.store_slot) s.add(r.store_slot); });
      Object.keys(have).forEach((n) => s.add(n));
      return Array.from(s).sort();
    }, [routes, have]);
    const setCred = () => {
      if (!name || !val) return;
      jfetch("/cred", { method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name, value: val }) })
        .then((r) => { setMsg("satt: " + (r.detail || name)); setVal(""); setName("");
                       setTick((t) => t + 1); })
        .catch((e) => setMsg("feil: " + e));
    };
    const body = slots.map((n) => {
      const k = have[n];
      return h("tr", { key: n, className: "border-t border-border/60" },
        h("td", { className: TD + " font-mono text-xs" }, n),
        h("td", { className: TD }, k
          ? h(Badge, { tone: "success", className: "text-xs" }, "satt")
          : h(Badge, { tone: "destructive", className: "text-xs" }, "mangler ⚠")),
        h("td", { className: TD + " font-mono text-xs text-muted-foreground" }, k ? k.fingerprint : "—"),
        h("td", { className: TD + " text-muted-foreground whitespace-nowrap" }, k ? k.mtime : ""));
    });
    const form = h("div", { className: "flex flex-wrap items-center gap-2" },
      h("input", { className: INPUT, placeholder: "SLOT_NAVN (A-Z_)", value: name,
        onChange: (e) => setName(e.target.value.toUpperCase()) }),
      h("input", { className: INPUT, type: "password", value: val,
        placeholder: "verdi (write-only — vises aldri igjen)",
        style: { flex: "1 1 280px", minWidth: "280px" },
        onChange: (e) => setVal(e.target.value) }),
      h(Button, { size: "sm", outlined: true, disabled: !name || !val, onClick: setCred }, "sett / rotér"));
    const content = h("div", { className: "flex flex-col gap-3" },
      Table(["slot", "i store", "fingeravtrykk", "sist satt"], body),
      form,
      msg ? h("div", { className: "text-sm border border-border bg-background/40 px-3 py-2 cursor-pointer break-words",
        onClick: () => setMsg(null) }, msg) : null,
      h("p", { className: "text-xs text-muted-foreground" },
        "Sudo-passord er kraftig: vurder heller en scoped NOPASSWD-sudoers-linje "
        + "på målverten (ingen hemmelighet lagres). Creds settes her kun av deg."));
    return Section({ title: "Creds-lager", badge: slots.length,
      sub: "verdier bor KUN i .11-storen (write-only) — her vises navn/fingeravtrykk" }, content);
  }

  function TilgangPage() {
    const { data } = useData("/routes", 0);
    const routes = (data && data.routes) || [];
    const hosts = new Set();
    const methods = new Set();
    let aktive = 0;
    routes.forEach((r) => {
      if (r.from_host) hosts.add(r.from_host);
      if (r.to_host) hosts.add(r.to_host);
      if (r.method) methods.add(r.method);
      if (r.status === "aktiv") aktive += 1;
    });
    return h("div", { className: "flex flex-col gap-4 p-4" },
      h("p", { className: "text-sm text-muted-foreground max-w-3xl" },
        "Kartet over hvem som når hva på tvers av maskinene, og det write-only "
        + "creds-lageret agentene og du deler. Hemmeligheter forlater aldri "
        + ".11-storen — grafen og denne sida bærer kun navn og fingeravtrykk."),
      h("div", { style: GRID },
        tile(String(routes.length), "ruter totalt"),
        tile(String(aktive), "aktive ruter"),
        tile(String(methods.size), "metoder"),
        tile(String(hosts.size), "unike verter")),
      h(Matrix, null),
      h(CredStore, { routes: routes }));
  }

  if (window.__HERMES_PLUGINS__ && typeof window.__HERMES_PLUGINS__.register === "function") {
    window.__HERMES_PLUGINS__.register("tilgang", TilgangPage);
  }
})();
