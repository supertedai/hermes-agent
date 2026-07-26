/**
 * Funn — GUI-ankeret for funn-loopen (BL-2368). NATIVE: bygget med Nous DS-
 * komponentene fra plugin-SDK-en (Card/CardHeader/CardTitle/CardContent/Badge)
 * + Hermes' egne tailwind-klasser — samme komponentbibliotek som Keys/Skills/
 * Plugins-sidene. Ingen håndrullet CSS (style.css er tom med vilje).
 */
(function () {
  "use strict";

  const SDK = window.__HERMES_PLUGIN_SDK__;
  if (!SDK) return;
  const { React } = SDK;
  const h = React.createElement;
  const { Card, CardHeader, CardTitle, CardContent, Badge } = SDK.components;
  const { useState, useEffect } = SDK.hooks;

  const API = "/api/plugins/funn";
  const jfetch = (p) =>
    SDK.fetchJSON ? SDK.fetchJSON(API + p)
      : SDK.authedFetch ? SDK.authedFetch(API + p).then((r) => r.json())
      : fetch(API + p).then((r) => r.json());

  function useData(path) {
    const [data, setData] = useState(null);
    const [err, setErr] = useState(null);
    useEffect(() => {
      let alive = true;
      const load = () => jfetch(path)
        .then((d) => { if (alive) { setData(d); setErr(null); } })
        .catch((e) => alive && setErr(String(e)));
      load();
      const t = setInterval(load, 90000);
      return () => { alive = false; clearInterval(t); };
    }, [path]);
    return { data, err };
  }

  // Badge-toner — kun DS-gyldige (secondary/success/destructive/outline)
  const catTone = (c) => c === "bug" ? "destructive"
    : c === "architecture_gap" || c === "directive" ? "secondary" : "outline";
  const stTone = (s) => s === "implemented" ? "success"
    : String(s).startsWith("blocked") ? "destructive"
    : s === "proposed" ? "secondary" : "outline";

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

  function LoopStatus() {
    const { data } = useData("/summary");
    if (!data) return h("p", { className: "text-sm text-muted-foreground" }, "Laster …");
    const un = ((data.unscanned || [])[0] || {}).n;
    const wms = data.watermarks || [];
    const stats = (data.status || []).slice(0, 5)
      .concat([{ status: "uskannede turns", n: un != null ? un : "?" }]);
    return h("div", { className: "flex flex-col gap-4" },
      h("div", { style: GRID },
        stats.map((s) => h("div", { key: s.status, className: "border border-border bg-background/40 px-3 py-2" },
          h("div", { className: "text-2xl font-semibold tabular-nums leading-none" }, String(s.n)),
          h("div", { className: "text-[0.6875rem] uppercase tracking-wide text-muted-foreground mt-1 break-words" }, s.status)))),
      Section({ title:"Sveise-status", sub: "sync hver 6.t (cron på .13 — se /cron)" },
        Table(["kilde", "watermark (msg-id)", "sist synket"],
          wms.map((w) => h("tr", { key: w.id, className: "border-t border-border/60" },
            h("td", { className: TD + " font-medium" }, (w.id || "").replace("hermes_chat_weld::", "")),
            h("td", { className: TD + " font-mono text-xs text-muted-foreground" }, String(w.last_msg_id)),
            h("td", { className: TD + " text-muted-foreground" }, (w.updated || "").slice(0, 19)))))),
      Section({ title:"Siste proposals", sub: "hele draineren — chat-funn er én av strømmene inn" },
        Table(["tittel", "opphav", "status", "når"],
          (data.latest || []).map((p, i) => h("tr", { key: i, className: "border-t border-border/60" },
            h("td", { className: TD + " font-medium" }, p.title),
            h("td", { className: TD + " text-muted-foreground" }, p.origin),
            h("td", { className: TD }, h(Badge, { tone: stTone(p.status), className: "text-xs" }, p.status)),
            h("td", { className: TD + " text-muted-foreground whitespace-nowrap" }, (p.created || "").slice(0, 16)))))));
  }

  function ChatFindings() {
    const { data, err } = useData("/findings");
    const [open, setOpen] = useState(null);
    const rows = (data && data.findings) || [];
    const body = [];
    rows.forEach((f, i) => {
      const key = f.title + i;
      body.push(h("tr", { key, className: "border-t border-border/60 cursor-pointer hover:bg-muted/20",
          onClick: () => setOpen(open === key ? null : key) },
        h("td", { className: TD + " font-medium" }, f.title),
        h("td", { className: TD }, h(Badge, { tone: catTone(f.category), className: "text-xs" }, f.category)),
        h("td", { className: TD + " tabular-nums" }, f.confidence != null ? Number(f.confidence).toFixed(2) : ""),
        h("td", { className: TD }, f.bl_number
          ? h("code", { className: "text-xs font-mono border border-border bg-background/40 px-1.5 py-0.5 whitespace-nowrap" },
              "BL-" + f.bl_number + " → " + (f.assigned_agent || "").replace("symbiose-", ""))
          : h("span", { className: "text-xs text-muted-foreground" }, "u-triagert")),
        h("td", { className: TD }, h(Badge, { tone: stTone(f.status), className: "text-xs" }, f.status)),
        h("td", { className: TD + " text-muted-foreground" }, (f.source || "").replace("chat:", "")),
        h("td", { className: TD + " text-muted-foreground whitespace-nowrap" }, (f.created || "").slice(0, 16))));
      if (open === key) {
        body.push(h("tr", { key: key + "-x", className: "border-t border-border/60 bg-background/40" },
          h("td", { colSpan: 7, className: "p-3 space-y-2" },
            h("div", null,
              h("div", { className: "text-[0.6875rem] uppercase tracking-wide text-muted-foreground" }, "Bruker"),
              h("div", { className: "text-sm whitespace-pre-wrap" }, f.user_msg || "—")),
            h("div", null,
              h("div", { className: "text-[0.6875rem] uppercase tracking-wide text-muted-foreground" }, "Assistent"),
              h("div", { className: "text-sm whitespace-pre-wrap" }, f.assistant_msg || "—")))));
      }
    });
    return Section({ title: "Chat-funn", badge: rows.length,
        sub: "høstet av 120B fra Hermes + OpenWebUI-samtaler — klikk en rad for chat-evidens" },
      err ? h("p", { className: "text-sm text-destructive" }, "utilgjengelig: " + err)
        : Table(["funn", "type", "sikkerhet", "BL → agent", "status", "flate", "når"], body));
  }

  function FunnPage() {
    return h("div", { className: "flex flex-col gap-4 p-4" },
      h("p", { className: "text-sm text-muted-foreground max-w-3xl" },
        "Alt du og agentene sier i Hermes-chatten og OpenWebUI høstes for operasjonelle funn "
        + "(feil, gaps, påpekninger) → proposals (propose-first, med chat-evidens) → drainer → BL → agent. "
        + "Klinisk innhold høstes aldri (A7)."),
      h(LoopStatus, null),
      h(ChatFindings, null));
  }

  if (window.__HERMES_PLUGINS__ && typeof window.__HERMES_PLUGINS__.register === "function") {
    window.__HERMES_PLUGINS__.register("funn", FunnPage);
  }
})();
