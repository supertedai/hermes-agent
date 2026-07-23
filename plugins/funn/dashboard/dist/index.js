/**
 * Funn — GUI-ankeret for funn-loopen (BL-2368).
 *
 * Hele sveisen på ett brett: chat (Hermes GUI + OpenWebUI) → ConversationTurn
 * → 120B-høster → ImprovementProposal (proposed) → drainer-triage → BL → agent.
 * Read-only: triage/BL skjer i drainer/gate-laget, ikke her.
 */
(function () {
  "use strict";

  const SDK = window.__HERMES_PLUGIN_SDK__;
  if (!SDK) return;
  const { React } = SDK;
  const h = React.createElement;
  const { Card, CardContent } = SDK.components;
  const { useState, useEffect } = SDK.hooks;

  const API = "/api/plugins/funn";
  const jfetch = (path) =>
    SDK.fetchJSON ? SDK.fetchJSON(API + path)
      : SDK.authedFetch ? SDK.authedFetch(API + path).then((r) => r.json())
      : fetch(API + path).then((r) => r.json());

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

  const CAT = { bug: "fn-cat-bug", architecture_gap: "fn-cat-gap",
                weakness: "fn-cat-weak", directive: "fn-cat-dir" };
  const ST = (s) =>
    s === "proposed" ? "fn-st-proposed"
      : s === "implemented" ? "fn-st-done"
      : String(s).startsWith("blocked") ? "fn-st-blocked" : "fn-st-other";

  function ChatFindings() {
    const { data, err } = useData("/findings");
    const [open, setOpen] = useState(null);
    if (err) return h("div", { className: "fn-err" }, "utilgjengelig: " + err);
    const rows = (data && data.findings) || [];
    return h("div", { className: "fn-section" },
      h("h3", { className: "fn-h" }, "Chat-funn ",
        h("span", { className: "fn-dim" },
          "høstet av 120B fra Hermes + OpenWebUI-samtaler — klikk for chat-evidens")),
      h("table", { className: "fn-table" },
        h("thead", null, h("tr", null,
          ["funn", "type", "sikkerhet", "status", "flate", "når"].map((c) =>
            h("th", { key: c }, c)))),
        h("tbody", null, rows.flatMap((f, i) => {
          const key = f.title + i;
          const out = [h("tr", { key, className: "fn-row",
                              onClick: () => setOpen(open === key ? null : key) },
            h("td", { className: "fn-title" }, f.title),
            h("td", null, h("span", { className: "fn-badge " + (CAT[f.category] || "") },
              f.category)),
            h("td", null, f.confidence != null ? Number(f.confidence).toFixed(2) : ""),
            h("td", null, h("span", { className: "fn-badge " + ST(f.status) }, f.status)),
            h("td", null, (f.source || "").replace("chat:", "")),
            h("td", { className: "fn-dim" }, (f.created || "").slice(0, 16)))];
          if (open === key) {
            out.push(h("tr", { key: key + "-x", className: "fn-evidence" },
              h("td", { colSpan: 6 },
                h("div", { className: "fn-ev-block" },
                  h("div", { className: "fn-ev-label" }, "BRUKER:"),
                  h("div", { className: "fn-ev-text" }, f.user_msg || "—"),
                  h("div", { className: "fn-ev-label" }, "ASSISTENT:"),
                  h("div", { className: "fn-ev-text" }, f.assistant_msg || "—")))));
          }
          return out;
        }))));
  }

  function LoopStatus() {
    const { data } = useData("/summary");
    if (!data) return null;
    const un = ((data.unscanned || [])[0] || {}).n;
    const wms = data.watermarks || [];
    return h("div", null,
      h("div", { className: "fn-stats" },
        (data.status || []).slice(0, 5).map((s) =>
          h(Card, { key: s.status }, h(CardContent, { className: "fn-stat" },
            h("div", { className: "fn-stat-n" }, String(s.n)),
            h("div", { className: "fn-stat-l" }, s.status)))),
        h(Card, null, h(CardContent, { className: "fn-stat" },
          h("div", { className: "fn-stat-n" }, String(un != null ? un : "?")),
          h("div", { className: "fn-stat-l" }, "uskannede turns")))),
      h("div", { className: "fn-section" },
        h("h3", { className: "fn-h" }, "Sveise-status ",
          h("span", { className: "fn-dim" }, "sync hver 6.t (cron på .13 — se /cron)")),
        h("table", { className: "fn-table" },
          h("thead", null, h("tr", null, ["kilde", "watermark (msg-id)", "sist synket"]
            .map((c) => h("th", { key: c }, c)))),
          h("tbody", null, wms.map((w) =>
            h("tr", { key: w.id, className: "fn-row" },
              h("td", { className: "fn-title" }, (w.id || "").replace("hermes_chat_weld::", "")),
              h("td", null, String(w.last_msg_id)),
              h("td", { className: "fn-dim" }, (w.updated || "").slice(0, 19))))))),
      h("div", { className: "fn-section" },
        h("h3", { className: "fn-h" }, "Siste proposals (alle kilder) ",
          h("span", { className: "fn-dim" }, "hele draineren — chat-funn er én av strømmene inn")),
        h("table", { className: "fn-table" },
          h("thead", null, h("tr", null, ["tittel", "opphav", "status", "når"]
            .map((c) => h("th", { key: c }, c)))),
          h("tbody", null, (data.latest || []).map((p, i) =>
            h("tr", { key: i, className: "fn-row" },
              h("td", { className: "fn-title" }, p.title),
              h("td", { className: "fn-dim" }, p.origin),
              h("td", null, h("span", { className: "fn-badge " + ST(p.status) }, p.status)),
              h("td", { className: "fn-dim" }, (p.created || "").slice(0, 16))))))));
  }

  function FunnPage() {
    return h("div", { className: "fn-wrap" },
      h("div", { className: "fn-header" },
        h("h2", null, "Funn — chat → BL-loopen"),
        h("p", { className: "fn-sub" },
          "Alt du og agentene sier i Hermes-chatten og OpenWebUI høstes for "
          + "operasjonelle funn (feil, gaps, påpekninger). Funn blir proposals "
          + "(propose-first, med chat-evidens), draineren triagerer dem til BL, "
          + "og en agent tar arbeidet. Klinisk innhold høstes aldri (A7).")),
      h(LoopStatus, null),
      h(ChatFindings, null));
  }

  if (window.__HERMES_PLUGINS__ && typeof window.__HERMES_PLUGINS__.register === "function") {
    window.__HERMES_PLUGINS__.register("funn", FunnPage);
  }
})();
