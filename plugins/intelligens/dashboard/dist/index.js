/**
 * Intelligens — meta-loopen synlig (BL-2409, ADR-019).
 *
 * «Ble Opus smartere, og hva forårsaket det?» Dette vinduet viser den ærlige,
 * deskriptive målingen: Intelligens-Indeksens trajektorie, det forseglede
 * baseline-ankeret (målstangen), og før/etter-evalen mot det. Read-only —
 * segling er Mortens governance, evalen skrives av cron. Aldri et optimeringsmål.
 */
(function () {
  "use strict";

  const SDK = window.__HERMES_PLUGIN_SDK__;
  if (!SDK) return;
  const { React } = SDK;
  const h = React.createElement;
  const { Card, CardContent } = SDK.components;
  const { useState, useEffect } = SDK.hooks;

  const jfetch = (path) =>
    SDK.fetchJSON ? SDK.fetchJSON("/api/plugins/intelligens" + path)
      : SDK.authedFetch ? SDK.authedFetch("/api/plugins/intelligens" + path).then((r) => r.json())
      : fetch("/api/plugins/intelligens" + path).then((r) => r.json());

  function useLoop() {
    const [d, setD] = useState(null);
    const [err, setErr] = useState(null);
    useEffect(() => {
      let alive = true;
      const load = () => jfetch("/loop")
        .then((x) => { if (alive) { setD(x); setErr(null); } })
        .catch((e) => alive && setErr(String(e)));
      load();
      const t = setInterval(load, 120000);
      return () => { alive = false; clearInterval(t); };
    }, []);
    return { d, err };
  }

  const VERD = {
    improved: { t: "↑ forbedret", c: "iq-v-up" },
    regressed: { t: "↓ regresjon", c: "iq-v-down" },
    stable: { t: "→ stabil", c: "iq-v-flat" },
    low_confidence: { t: "⚠ lav tillit (stale)", c: "iq-v-warn" },
    no_data: { t: "ingen data", c: "iq-v-flat" },
  };

  // enkel inline-sparkline over ii-trajektorien (nyeste til høyre)
  function Spark(pts) {
    if (!pts.length) return null;
    const vals = pts.slice().reverse();
    const min = Math.min.apply(null, vals), max = Math.max.apply(null, vals);
    const rng = max - min || 1;
    const W = 320, H = 40, step = W / Math.max(vals.length - 1, 1);
    const d = vals.map((v, i) =>
      (i === 0 ? "M" : "L") + (i * step).toFixed(1) + "," +
      (H - ((v - min) / rng) * H).toFixed(1)).join(" ");
    return h("svg", { className: "iq-spark", viewBox: `0 0 ${W} ${H}`, width: W, height: H },
      h("path", { d, fill: "none", stroke: "currentColor", strokeWidth: 1.5 }));
  }

  function IntelligensView() {
    const { d, err } = useLoop();
    if (err) return h("div", { className: "iq-wrap" }, h("div", { className: "iq-err" }, "Feil: " + err));
    if (!d) return h("div", { className: "iq-wrap" }, h("div", { className: "iq-loading" }, "laster meta-loopen…"));

    const ii = d.ii || [];
    const latestIi = ii[0] || {};
    const evals = d.eval || [];
    const latestEval = evals[0] || {};
    const oper = (d.operationalization || [])[0] || {};
    const v2 = (d.baselines || []).find((b) => b.version === "v2") || {};
    const v1 = (d.baselines || []).find((b) => b.version === "v1") || {};
    const verd = VERD[latestEval.verdict] || VERD.no_data;

    return h("div", { className: "iq-wrap" },
      h("div", { className: "iq-header" },
        h("h2", null, "Intelligens — ble Opus smartere?"),
        h("p", { className: "iq-sub" },
          "Den ærlige, deskriptive målingen (ADR-019). Aldri et optimeringsmål — "
          + "den informerer, den styrer ingen auto-mutasjon. Segling er Mortens governance.")),

      // topp-kort: siste eval-verdict + II
      h("div", { className: "iq-stats" },
        h(Card, null, h(CardContent, { className: "iq-stat " + verd.c },
          h("div", { className: "iq-stat-n" }, verd.t),
          h("div", { className: "iq-stat-l" }, "eval-dom (held-out vs baseline)"))),
        h(Card, null, h(CardContent, { className: "iq-stat" },
          h("div", { className: "iq-stat-n" }, latestEval.current != null ? Number(latestEval.current).toFixed(3) : "—"),
          h("div", { className: "iq-stat-l" }, "held-out nå"))),
        h(Card, null, h(CardContent, { className: "iq-stat" },
          h("div", { className: "iq-stat-n" }, v2.baseline != null ? Number(v2.baseline).toFixed(3) : "—"),
          h("div", { className: "iq-stat-l" }, "forseglet baseline (v2)"))),
        h(Card, null, h(CardContent, { className: "iq-stat" },
          h("div", { className: "iq-stat-n" }, latestIi.ii != null ? Number(latestIi.ii).toFixed(3) : "—"),
          h("div", { className: "iq-stat-l" }, "intelligens-indeks (siste dag)")))),

      // eval-detalj
      h("div", { className: "iq-section" },
        h("h3", { className: "iq-h" }, "Før/etter-eval ",
          h("span", { className: "iq-dim" },
            "delta " + (latestEval.delta != null ? (latestEval.delta > 0 ? "+" : "") + Number(latestEval.delta).toFixed(4) : "—")
            + " · ferskhet " + (latestEval.fresh_frac != null ? Math.round(latestEval.fresh_frac * 100) + "%" : "—")
            + " · " + (latestEval.at || "").slice(0, 16))),
        h("div", { className: "iq-dim iq-note" },
          "Held-out re-kjøres av gym-en; delta≠0 krever tid etter segl. Snapshots hver 6t (se /cron).")),

      // baselines
      h("div", { className: "iq-section" },
        h("h3", { className: "iq-h" }, "Forseglede baseliner ", h("span", { className: "iq-dim" }, "målstangen — uforanderlig etter segl")),
        h("table", { className: "iq-table" },
          h("thead", null, h("tr", null, ["versjon", "status", "held-out", "baseline", "forseglet av"].map((c) => h("th", { key: c }, c)))),
          h("tbody", null, (d.baselines || []).map((b) =>
            h("tr", { key: b.version, className: "iq-row" },
              h("td", { className: "iq-name" }, b.version + (b.version === "v2" ? " (aktiv)" : b.version === "v1" ? " (historisk)" : "")),
              h("td", null, h("span", { className: "iq-badge " + (b.status === "sealed" ? "iq-sealed" : "iq-proposed") }, b.status)),
              h("td", null, String(b.n_held_out || "")),
              h("td", null, b.baseline != null ? Number(b.baseline).toFixed(4) : "—"),
              h("td", { className: "iq-dim" }, b.sealed_by || "—")))))),

      // II-trajektorie
      h("div", { className: "iq-section" },
        h("h3", { className: "iq-h" }, "Intelligens-indeks over tid ",
          h("span", { className: "iq-dim" }, (oper.active_dims || "") + " aktiv · " + (oper.pending_dims || "") + " venter baseline")),
        h("div", { className: "iq-sparkwrap" }, Spark(ii.map((p) => p.ii).filter((x) => x != null))),
        h("table", { className: "iq-table" },
          h("thead", null, h("tr", null, ["dag", "II", "problem_solving", "kalibrering", "n", "status"].map((c) => h("th", { key: c }, c)))),
          h("tbody", null, ii.slice(0, 14).map((p) =>
            h("tr", { key: p.day, className: "iq-row" },
              h("td", { className: "iq-name" }, p.day),
              h("td", null, p.ii != null ? Number(p.ii).toFixed(3) : "—"),
              h("td", null, p.problem_solving != null ? Number(p.problem_solving).toFixed(3) : "—"),
              h("td", null, p.calibration != null ? Number(p.calibration).toFixed(3) : "—"),
              h("td", { className: "iq-dim" }, String(p.n_exams || "")),
              h("td", { className: "iq-dim" }, p.status || "")))))),
      h("p", { className: "iq-foot" },
        "Goodhart-vern: indeksen er DESKRIPTIV (never_optimization_target). Blir den et optimeringsmål, ER det feilmoden. "
        + "Kausal attribusjon (hvilken endring) = P3; regresjon-alarm = P4 (etter bevist signal)."));
  }

  if (window.__HERMES_PLUGINS__ && typeof window.__HERMES_PLUGINS__.register === "function") {
    window.__HERMES_PLUGINS__.register("intelligens", IntelligensView);
  }
})();
