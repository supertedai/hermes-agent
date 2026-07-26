/**
 * Fleet Cron — /cron-override (BL-2363). NATIVE: bygget med Nous DS-
 * komponentene fra plugin-SDK-en (Card/CardHeader/CardTitle/CardContent/Badge/
 * Button) + Hermes' egne tailwind-klasser — samme komponentbibliotek som Keys/
 * Skills/Plugins-sidene. Ingen håndrullet CSS (style.css er tom med vilje).
 *
 * ÉN side for all planlagt kjøring i Symbiosen: Hermes' egne cron-jobber
 * (.15, native /api/cron-API med full forvaltning: opprett/pause/kjør nå)
 * + flåte-inventaret fra grafen (.11/.12/.13 crontab+launchd, samlet av
 * fleet_cron_collector hver time — read-only her; de eies av maskinene).
 */
(function () {
  "use strict";

  const SDK = window.__HERMES_PLUGIN_SDK__;
  if (!SDK) return;
  const { React } = SDK;
  const h = React.createElement;
  const { Card, CardHeader, CardTitle, CardContent, Badge, Button } = SDK.components;
  const { useState, useEffect, useMemo, useCallback } = SDK.hooks;

  const jfetch = (path, opts) =>
    SDK.fetchJSON ? SDK.fetchJSON(path, opts)
      : SDK.authedFetch ? SDK.authedFetch(path, opts).then((r) => r.json())
      : fetch(path, opts).then((r) => r.json());

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

  const HOST_LABELS = {
    "13-morpheus": "Morpheus (.13 — Mac Studio)",
    "12-byopus": "byopus (.12 — Threadripper)",
    "11-cco": "CCO (.11 — jetstream)",
    "15-veriton": "Veriton (.15 — agenter)",
  };

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

  function KPI(tiles) {
    return h("div", { style: GRID },
      tiles.map((t) => h("div", { key: t.label, className: "border border-border bg-background/40 px-3 py-2" },
        h("div", { className: "text-2xl font-semibold tabular-nums leading-none" }, String(t.n)),
        h("div", { className: "text-[0.6875rem] uppercase tracking-wide text-muted-foreground mt-1 break-words" }, t.label))));
  }

  // Hermes-jobbene (.15) — full native forvaltning: pause/gjenoppta/kjør nå +
  // opprett ny jobb. rows/refresh løftes fra siden så KPI-tellerne matcher.
  function HermesJobs({ rows, err, refresh, setMsg }) {
    const [form, setForm] = useState({ name: "", schedule: "", prompt: "" });
    const act = (id, action) =>
      jfetch("/api/cron/jobs/" + encodeURIComponent(id) + "/" + action, { method: "POST" })
        .then(() => { setMsg(action + " ok"); refresh(); })
        .catch((e) => setMsg("feil: " + e));
    const create = () =>
      jfetch("/api/cron/jobs", { method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: form.name, schedule: form.schedule,
                               prompt: form.prompt, deliver: "local" }) })
        .then(() => { setMsg("jobb '" + form.name + "' opprettet");
                      setForm({ name: "", schedule: "", prompt: "" }); refresh(); })
        .catch((e) => setMsg("feil: " + e));
    const INPUT = "w-full border border-border bg-background px-2 py-1 text-sm";

    const table = Table(["navn", "schedule", "status", "handling"],
      rows.map((j) => {
        const id = j.id || j.job_id || j.name;
        const paused = j.paused === true || j.enabled === false;
        return h("tr", { key: id, className: "border-t border-border/60" },
          h("td", { className: TD + " font-medium" }, j.name || id),
          h("td", { className: TD + " font-mono text-xs text-muted-foreground" }, j.schedule || ""),
          h("td", { className: TD }, h(Badge, { tone: paused ? "secondary" : "success", className: "text-xs" },
            paused ? "pauset" : "aktiv")),
          h("td", { className: TD },
            h("div", { className: "flex flex-wrap gap-2" },
              h(Button, { size: "sm", outlined: true, onClick: () => act(id, paused ? "resume" : "pause") },
                paused ? "gjenoppta" : "pause"),
              h(Button, { size: "sm", onClick: () => act(id, "trigger") }, "kjør nå"))));
      }));

    const formRow = h("div", { className: "flex flex-col gap-2 border-t border-border/60 pt-3" },
      h("div", { className: "text-[0.6875rem] uppercase tracking-wide text-muted-foreground" }, "ny Hermes-jobb"),
      h("div", { className: "grid gap-2", style: { gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" } },
        h("input", { className: INPUT, placeholder: "navn", value: form.name,
                     onChange: (e) => setForm({ ...form, name: e.target.value }) }),
        h("input", { className: INPUT, placeholder: "cron-schedule (f.eks. 0 7 * * *)", value: form.schedule,
                     onChange: (e) => setForm({ ...form, schedule: e.target.value }) }),
        h("input", { className: INPUT, placeholder: "prompt/oppgave", value: form.prompt,
                     onChange: (e) => setForm({ ...form, prompt: e.target.value }) })),
      h("div", null,
        h(Button, { size: "sm", disabled: !form.schedule || !form.prompt, onClick: create }, "opprett jobb")));

    return Section({ title: "Hermes-jobber (.15)", badge: rows.length,
        sub: "native forvaltning — kjøres av Hermes her" },
      err ? h("p", { className: "text-sm text-destructive" }, "kunne ikke hente: " + err)
        : h("div", { className: "flex flex-col gap-4" }, table, formRow));
  }

  // Flåte-inventaret (.11/.12/.13) — read-only, gruppert per maskin.
  function FleetSection({ data, err }) {
    const byHost = useMemo(() => {
      const out = {};
      ((data && data.jobs) || []).forEach((j) => { (out[j.host] = out[j.host] || []).push(j); });
      return out;
    }, [data]);
    if (err) return Section({ title: "Flåte-registeret" },
      h("p", { className: "text-sm text-destructive" }, "utilgjengelig: " + err));
    return h("div", { className: "flex flex-col gap-4" },
      Object.keys(byHost).sort().map((host) =>
        h(React.Fragment, { key: host },
          Section({ title: HOST_LABELS[host] || host, badge: byHost[host].length,
              sub: "eies av maskinen; samlet av kollektoren hver time" },
            Table(["jobb", "type", "schedule", "kommando"],
              byHost[host].map((j, i) =>
                h("tr", { key: host + i, className: "border-t border-border/60" },
                  h("td", { className: TD + " font-medium" }, j.label || "—"),
                  h("td", { className: TD }, h(Badge, { tone: "outline", className: "text-xs" }, j.scheduler)),
                  h("td", { className: TD + " font-mono text-xs text-muted-foreground" }, j.schedule),
                  h("td", { className: TD + " font-mono text-xs text-muted-foreground", title: j.command },
                    (j.command || "").slice(0, 90)))))))));
  }

  function FleetCronPage() {
    const [msg, setMsg] = useState(null);
    const [tick, setTick] = useState(0);
    const refresh = useCallback(() => setTick((t) => t + 1), []);
    const { data: cron, err: cronErr } = useData("/api/cron/jobs", tick);
    const { data: fleet, err: fleetErr } = useData("/api/plugins/fleetcron/fleet", 0);

    const hermes = (cron && (cron.jobs || cron)) || [];
    const hRows = Array.isArray(hermes) ? hermes : [];
    const paused = hRows.filter((j) => j.paused === true || j.enabled === false).length;
    const fleetJobs = (fleet && fleet.jobs) || [];
    const hosts = new Set(fleetJobs.map((j) => j.host)).size;

    return h("div", { className: "flex flex-col gap-4 p-4" },
      h("p", { className: "text-sm text-muted-foreground max-w-3xl" },
        "Alt som kjører på klokke, ett brett: Hermes-jobbene forvaltes her; "
        + "flåten (.11/.12/.13) samles automatisk av fleet_cron_collector hver time — "
        + "nye cron/launchd-jobber dukker opp av seg selv."),
      msg ? h("div", { className: "border border-border bg-background/40 px-3 py-2 text-sm cursor-pointer",
          onClick: () => setMsg(null) },
        h("span", { className: "text-muted-foreground" }, msg + "  (klikk for å lukke)")) : null,
      KPI([
        { n: hRows.length, label: "Hermes-jobber (.15)" },
        { n: hRows.length - paused, label: "aktive" },
        { n: paused, label: "pausede" },
        { n: fleetJobs.length, label: "flåte-jobber i grafen" },
        { n: hosts, label: "maskiner" },
      ]),
      h(HermesJobs, { rows: hRows, err: cronErr, refresh, setMsg }),
      h(FleetSection, { data: fleet, err: fleetErr }));
  }

  if (window.__HERMES_PLUGINS__ && typeof window.__HERMES_PLUGINS__.register === "function") {
    window.__HERMES_PLUGINS__.register("fleetcron", FleetCronPage);
  }
})();
