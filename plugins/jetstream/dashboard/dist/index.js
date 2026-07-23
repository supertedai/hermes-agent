/**
 * Jetstream — Dashboard Plugin (BL-2348)
 *
 * Verden→Symbiose ingest-registeret: viser alle :IngestSourceSpec-noder
 * (seedet fra compose-masteren av tools/jetstream_registry.py i AGI-repoet),
 * gruppert per domene, med kind, migreringsstatus og konsum-kontrakt.
 *
 * Samme mønster som kanban-pluginen: plain IIFE, ingen byggesteg,
 * window.__HERMES_PLUGIN_SDK__ for React + shadcn-primitiver, backend på
 * /api/plugins/jetstream/ (fast Cypher server-side, read-only).
 */
(function () {
  "use strict";

  const SDK = window.__HERMES_PLUGIN_SDK__;
  if (!SDK) return;

  const { React } = SDK;
  const h = React.createElement;
  const { Card, CardContent, Badge } = SDK.components;
  const { useState, useEffect, useMemo } = SDK.hooks;

  const API = "/api/plugins/jetstream";

  function useFetch(path) {
    const [data, setData] = useState(null);
    const [err, setErr] = useState(null);
    useEffect(() => {
      let alive = true;
      // authedFetch/fetchJSON: dashboardets sesjons-token følger med (samme
      // mønster som kanban — /api/plugins/* er bak auth-middleware)
      const load = () =>
        SDK.fetchJSON ? SDK.fetchJSON(API + path)
          : SDK.authedFetch ? SDK.authedFetch(API + path).then((r) => r.json())
          : fetch(API + path).then((r) => r.json());
      load()
        .then((d) => alive && setData(d))
        .catch((e) => alive && setErr(String(e)));
      const t = setInterval(() => load().then((d) => alive && setData(d)).catch(() => {}), 30000);
      return () => { alive = false; clearInterval(t); };
    }, [path]);
    return { data, err };
  }

  const MIGRATION_BADGE = {
    legacy_daemon: { label: "legacy-daemon", cls: "js-badge-legacy" },
    jetstream_worker: { label: "jetstream", cls: "js-badge-live" },
  };

  function SourceRow({ s }) {
    const mig = MIGRATION_BADGE[s.migration] || { label: s.migration || "?", cls: "" };
    const consumerOk = (s.consumers || 0) > 0;
    return h("tr", { className: "js-row" },
      h("td", { className: "js-name" }, s.name),
      h("td", null, h(Badge, { variant: "outline" }, s.kind || "?")),
      h("td", null, h("span", { className: "js-mig " + mig.cls }, mig.label)),
      h("td", null,
        consumerOk
          ? h("span", { className: "js-consumer-ok" }, `${s.consumers} konsument${s.consumers > 1 ? "er" : ""}`)
          : h("span", { className: "js-consumer-missing", title: "Konsum-kontrakten: kilde uten deklarert konsument strupes/flagges (20:1-lærdommen)" }, "ingen konsument ⚠")),
      h("td", { className: "js-endpoint" }, s.endpoint || ""),
      h("td", { className: "js-container" }, s.container || "")
    );
  }

  function DomainSection({ domain, rows }) {
    return h("div", { className: "js-domain" },
      h("h3", { className: "js-domain-title" }, domain, " ",
        h("span", { className: "js-domain-count" }, `(${rows.length})`)),
      h("table", { className: "js-table" },
        h("thead", null, h("tr", null,
          ["kilde", "type", "status", "konsum-kontrakt", "endepunkt", "legacy-container"]
            .map((c) => h("th", { key: c }, c)))),
        h("tbody", null, rows.map((s) => h(SourceRow, { key: s.name, s })))));
  }

  function JetstreamView() {
    const { data: sum } = useFetch("/summary");
    const { data, err } = useFetch("/sources");

    const byDomain = useMemo(() => {
      const out = {};
      (data && data.sources ? data.sources : []).forEach((s) => {
        (out[s.domain || "general"] = out[s.domain || "general"] || []).push(s);
      });
      return out;
    }, [data]);

    if (err) return h("div", { className: "js-wrap" }, h(Card, null, h(CardContent, null, "Feil: " + err)));

    const undeclared = (data && data.sources ? data.sources : []).filter((s) => !(s.consumers > 0)).length;

    return h("div", { className: "js-wrap" },
      h("div", { className: "js-header" },
        h("h2", null, "Jetstream — verden → Symbiose"),
        h("p", { className: "js-sub" },
          "Kilderegisteret (:IngestSourceSpec). Alle eksterne ingest-flater, konsum-kontrakt og strangler-fig-migreringsstatus. Seedet fra compose-masteren; sannhetskilden er grafen.")),
      sum && h("div", { className: "js-stats" },
        h(Card, null, h(CardContent, { className: "js-stat" },
          h("div", { className: "js-stat-n" }, String(sum.total || 0)),
          h("div", { className: "js-stat-l" }, "kilder"))),
        h(Card, null, h(CardContent, { className: "js-stat" },
          h("div", { className: "js-stat-n" }, String((sum.by_migration || {}).jetstream_worker || 0)),
          h("div", { className: "js-stat-l" }, "migrert til jetstream"))),
        h(Card, null, h(CardContent, { className: "js-stat" },
          h("div", { className: "js-stat-n" }, String((sum.by_migration || {}).legacy_daemon || 0)),
          h("div", { className: "js-stat-l" }, "legacy-daemons"))),
        h(Card, null, h(CardContent, { className: "js-stat js-stat-warn" },
          h("div", { className: "js-stat-n" }, String(undeclared)),
          h("div", { className: "js-stat-l" }, "uten konsument ⚠")))),
      Object.keys(byDomain).sort().map((d) =>
        h(DomainSection, { key: d, domain: d, rows: byDomain[d] })),
      !data && h("div", { className: "js-loading" }, "laster registeret…"));
  }

  if (window.__HERMES_PLUGINS__ && typeof window.__HERMES_PLUGINS__.register === "function") {
    window.__HERMES_PLUGINS__.register("jetstream", JetstreamView);
  }
})();
