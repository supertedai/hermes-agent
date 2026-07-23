/**
 * Tilgang — access-kartet + creds-lager (BL-2378).
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
  const { Card, CardContent } = SDK.components;
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

  const ST = {
    aktiv: "tg-st-live", mangler: "tg-st-missing",
    inaktiv: "tg-st-off", ukjent: "tg-st-unknown",
  };

  function Matrix() {
    const { data, err } = useData("/routes", 0);
    if (err) return h("div", { className: "tg-err" }, "kart utilgjengelig: " + err);
    const rows = (data && data.routes) || [];
    return h("div", { className: "tg-section" },
      h("h3", { className: "tg-h" }, "Tilgangskart ",
        h("span", { className: "tg-dim" }, "hvem når hva, og hvorfor")),
      h("table", { className: "tg-table" },
        h("thead", null, h("tr", null,
          ["fra", "til", "metode", "identitet", "formål", "status"].map((c) =>
            h("th", { key: c }, c)))),
        h("tbody", null, rows.map(function (r, i) {
          const badge = h("span", { className: "tg-badge " + (ST[r.status] || "") },
                          r.status || "?");
          return h("tr", { key: i, className: "tg-row" },
            h("td", { className: "tg-host" }, r.from_host),
            h("td", { className: "tg-host" }, r.to_host),
            h("td", null, r.method),
            h("td", { className: "tg-mono" }, r.credential || ""),
            h("td", { className: "tg-dim" }, r.purpose || ""),
            h("td", null, badge));
        }))));
  }

  function CredStore({ routes }) {
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
      (routes || []).forEach((r) => { if (r.store_slot) s.add(r.store_slot); });
      Object.keys(have).forEach((n) => s.add(n));
      return Array.from(s).sort();
    }, [routes, have]);
    const setCred = () => {
      jfetch("/cred", { method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, value: val }) })
        .then((r) => { setMsg("satt: " + (r.detail || name)); setVal(""); setName("");
                       setTick((t) => t + 1); })
        .catch((e) => setMsg("feil: " + e));
    };
    return h("div", { className: "tg-section" },
      h("h3", { className: "tg-h" }, "Creds-lager ",
        h("span", { className: "tg-dim" },
          "verdier bor KUN i .11-storen (write-only) — her vises navn/fingeravtrykk")),
      msg && h("div", { className: "tg-msg", onClick: () => setMsg(null) }, msg),
      h("table", { className: "tg-table" },
        h("thead", null, h("tr", null,
          ["slot", "i store", "fingeravtrykk", "sist satt"].map((c) =>
            h("th", { key: c }, c)))),
        h("tbody", null, slots.map((n) => {
          const k = have[n];
          return h("tr", { key: n, className: "tg-row" },
            h("td", { className: "tg-mono" }, n),
            h("td", null, k
              ? h("span", { className: "tg-badge tg-st-live" }, "satt")
              : h("span", { className: "tg-badge tg-st-missing" }, "mangler ⚠")),
            h("td", { className: "tg-mono tg-dim" }, k ? k.fingerprint : "—"),
            h("td", { className: "tg-dim" }, k ? k.mtime : ""));
        }))),
      h("div", { className: "tg-form" },
        h("input", { className: "tg-input", placeholder: "SLOT_NAVN (A-Z_)",
                     value: name, onChange: (e) => setName(e.target.value.toUpperCase()) }),
        h("input", { className: "tg-input tg-wide", type: "password",
                     placeholder: "verdi (write-only — vises aldri igjen)",
                     value: val, onChange: (e) => setVal(e.target.value) }),
        h("button", { className: "tg-btn tg-go", disabled: !name || !val, onClick: setCred },
          "sett / rotér")),
      h("p", { className: "tg-hint" },
        "Sudo-passord er kraftig: vurder heller en scoped NOPASSWD-sudoers-linje "
        + "på målverten (ingen hemmelighet lagres). Creds settes her kun av deg."));
  }

  function TilgangPage() {
    const { data } = useData("/routes", 0);
    const routes = (data && data.routes) || [];
    return h("div", { className: "tg-wrap" },
      h("div", { className: "tg-header" },
        h("h2", null, "Tilgang — hvordan Symbiosen henger sammen"),
        h("p", { className: "tg-sub" },
          "Kartet over hvem som når hva på tvers av maskinene, og det write-only "
          + "creds-lageret agentene og du deler. Hemmeligheter forlater aldri "
          + ".11-storen — grafen og denne sida bærer kun navn og fingeravtrykk.")),
      h(Matrix, null),
      h(CredStore, { routes }));
  }

  if (window.__HERMES_PLUGINS__ && typeof window.__HERMES_PLUGINS__.register === "function") {
    window.__HERMES_PLUGINS__.register("tilgang", TilgangPage);
  }
})();
