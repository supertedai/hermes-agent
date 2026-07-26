/**
 * Intelligens — meta-loopen synlig (BL-2409, ADR-019). NATIVE: bygget med Nous
 * DS-komponentene fra plugin-SDK-en (Card/CardHeader/CardTitle/CardContent/Badge)
 * + Hermes' egne tailwind-klasser — samme komponentbibliotek som Keys/Skills/
 * Plugins-sidene. Ingen håndrullet CSS (style.css er tom med vilje).
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
  const { Card, CardHeader, CardTitle, CardContent, Badge } = SDK.components;
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

  const GRID = { display: "grid", gap: "0.5rem", gridTemplateColumns: "repeat(auto-fill, minmax(155px, 1fr))" };
  const TD = "py-1.5 pr-3 align-top";

  // Badge-toner — kun DS-gyldige (secondary/success/destructive/outline)
  const VERD = {
    improved: { t: "↑ forbedret", tone: "success" },
    regressed: { t: "↓ regresjon", tone: "destructive" },
    stable: { t: "→ stabil", tone: "secondary" },
    low_confidence: { t: "⚠ lav tillit (stale)", tone: "outline" },
    no_data: { t: "ingen data", tone: "outline" },
  };
  const sealTone = (s) => s === "sealed" ? "success" : "outline";
  const fx = (x, n) => x != null ? Number(x).toFixed(n) : "—";
  const signed = (x, n) => x != null ? (x > 0 ? "+" : "") + Number(x).toFixed(n) : "—";

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

  // Enkel inline-sparkline over ii-trajektorien (nyeste til høyre). currentColor
  // arver tekstfargen fra tailwind-klassen — ingen egen CSS-klasse.
  function Spark(pts) {
    if (!pts.length) return null;
    const vals = pts.slice().reverse();
    const min = Math.min.apply(null, vals), max = Math.max.apply(null, vals);
    const rng = max - min || 1;
    const W = 320, H = 40, step = W / Math.max(vals.length - 1, 1);
    const dpath = vals.map((v, i) =>
      (i === 0 ? "M" : "L") + (i * step).toFixed(1) + "," +
      (H - ((v - min) / rng) * H).toFixed(1)).join(" ");
    return h("svg", { className: "max-w-full block text-muted-foreground",
        viewBox: "0 0 " + W + " " + H, width: W, height: H },
      h("path", { d: dpath, fill: "none", stroke: "currentColor", strokeWidth: 1.5 }));
  }

  function IntelligensView() {
    const { d, err } = useLoop();
    if (err) return h("div", { className: "p-4" }, h("p", { className: "text-sm text-destructive" }, "Feil: " + err));
    if (!d) return h("div", { className: "p-4" }, h("p", { className: "text-sm text-muted-foreground" }, "laster meta-loopen …"));

    const ii = d.ii || [];
    const latestIi = ii[0] || {};
    const evals = d.eval || [];
    const latestEval = evals[0] || {};
    const oper = (d.operationalization || [])[0] || {};
    const v2 = (d.baselines || []).find((b) => b.version === "v2") || {};
    const verd = VERD[latestEval.verdict] || VERD.no_data;

    const evalSub = "delta " + signed(latestEval.delta, 4)
      + " · ferskhet " + (latestEval.fresh_frac != null ? Math.round(latestEval.fresh_frac * 100) + "%" : "—")
      + " · " + ((latestEval.at || "").slice(0, 16) || "—");

    return h("div", { className: "flex flex-col gap-4 p-4" },
      h("p", { className: "text-sm text-muted-foreground max-w-3xl" },
        "Den ærlige, deskriptive målingen (ADR-019): ble Opus smartere, og hva forårsaket det? "
        + "Aldri et optimeringsmål — den informerer, den styrer ingen auto-mutasjon. "
        + "Segling er Mortens governance; evalen skrives av cron."),

      h("div", { style: GRID },
        tile(fx(latestEval.current, 3), "held-out nå"),
        tile(fx(v2.baseline, 3), "forseglet baseline (v2)"),
        tile(fx(latestIi.ii, 3), "intelligens-indeks (siste dag)"),
        tile(signed(latestEval.delta, 3), "delta vs baseline")),

      Section({ title: "Før/etter-eval", badge: verd.t, badgeTone: verd.tone, sub: evalSub },
        h("p", { className: "text-sm text-muted-foreground" },
          "Held-out (vs forseglet baseline) re-kjøres av gym-en; delta≠0 krever tid etter segl. "
          + "Snapshots hver 6t (se /cron).")),

      Section({ title: "Forseglede baseliner", sub: "målstangen — uforanderlig etter segl" },
        Table(["versjon", "status", "held-out", "baseline", "forseglet av"],
          (d.baselines || []).map((b) =>
            h("tr", { key: b.version, className: "border-t border-border/60" },
              h("td", { className: TD + " font-medium" }, b.version + (b.version === "v2" ? " (aktiv)" : b.version === "v1" ? " (historisk)" : "")),
              h("td", { className: TD }, h(Badge, { tone: sealTone(b.status), className: "text-xs" }, b.status)),
              h("td", { className: TD + " tabular-nums" }, String(b.n_held_out || "")),
              h("td", { className: TD + " tabular-nums" }, fx(b.baseline, 4)),
              h("td", { className: TD + " text-muted-foreground" }, b.sealed_by || "—"))))),

      Section({ title: "Intelligens-indeks over tid",
          sub: (oper.active_dims != null ? oper.active_dims : "0") + " dimensjoner aktive · "
            + (oper.pending_dims != null ? oper.pending_dims : "0") + " venter baseline" },
        h("div", { className: "flex flex-col gap-3" },
          h("div", null, Spark(ii.map((p) => p.ii).filter((x) => x != null))),
          Table(["dag", "II", "problem_solving", "kalibrering", "n", "status"],
            ii.slice(0, 14).map((p) =>
              h("tr", { key: p.day, className: "border-t border-border/60" },
                h("td", { className: TD + " font-medium whitespace-nowrap" }, p.day),
                h("td", { className: TD + " tabular-nums" }, fx(p.ii, 3)),
                h("td", { className: TD + " tabular-nums" }, fx(p.problem_solving, 3)),
                h("td", { className: TD + " tabular-nums" }, fx(p.calibration, 3)),
                h("td", { className: TD + " tabular-nums text-muted-foreground" }, String(p.n_exams || "")),
                h("td", { className: TD + " text-muted-foreground" }, p.status || "")))))),

      h("p", { className: "text-xs text-muted-foreground max-w-3xl" },
        "Goodhart-vern: indeksen er DESKRIPTIV (never_optimization_target). Blir den et optimeringsmål, ER det feilmoden. "
        + "Kausal attribusjon (hvilken endring) = P3; regresjon-alarm = P4 (etter bevist signal)."));
  }

  if (window.__HERMES_PLUGINS__ && typeof window.__HERMES_PLUGINS__.register === "function") {
    window.__HERMES_PLUGINS__.register("intelligens", IntelligensView);
  }
})();
