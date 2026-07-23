/**
 * Fleet Cron — /cron-override (BL-2363)
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
  const { Card, CardContent } = SDK.components;
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

  function HermesJobs({ setMsg }) {
    const [tick, setTick] = useState(0);
    const refresh = useCallback(() => setTick((t) => t + 1), []);
    const { data, err } = useData("/api/cron/jobs", tick);
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
    const jobs = (data && (data.jobs || data)) || [];
    const rows = Array.isArray(jobs) ? jobs : [];
    return h("div", { className: "fc-section" },
      h("h3", { className: "fc-h" }, "Hermes-jobber (.15) ",
        h("span", { className: "fc-dim" }, "native forvaltning — kjøres av Hermes her")),
      err && h("div", { className: "fc-err" }, "kunne ikke hente: " + err),
      h("table", { className: "fc-table" },
        h("thead", null, h("tr", null, ["navn", "schedule", "status", "handling"]
          .map((c) => h("th", { key: c }, c)))),
        h("tbody", null, rows.map((j) => {
          const id = j.id || j.job_id || j.name;
          const paused = j.paused === true || j.enabled === false;
          return h("tr", { key: id, className: "fc-row" },
            h("td", { className: "fc-name" }, j.name || id),
            h("td", null, j.schedule || ""),
            h("td", null, paused
              ? h("span", { className: "fc-badge fc-paused" }, "pauset")
              : h("span", { className: "fc-badge fc-live" }, "aktiv")),
            h("td", { className: "fc-actions" },
              h("button", { className: "fc-btn",
                            onClick: () => act(id, paused ? "resume" : "pause") },
                paused ? "gjenoppta" : "pause"),
              h("button", { className: "fc-btn fc-go",
                            onClick: () => act(id, "trigger") }, "kjør nå")));
        }))),
      h("div", { className: "fc-form" },
        h("input", { className: "fc-input", placeholder: "navn",
                     value: form.name,
                     onChange: (e) => setForm({ ...form, name: e.target.value }) }),
        h("input", { className: "fc-input", placeholder: "cron-schedule (f.eks. 0 7 * * *)",
                     value: form.schedule,
                     onChange: (e) => setForm({ ...form, schedule: e.target.value }) }),
        h("input", { className: "fc-input fc-wide", placeholder: "prompt/oppgave",
                     value: form.prompt,
                     onChange: (e) => setForm({ ...form, prompt: e.target.value }) }),
        h("button", { className: "fc-btn fc-go",
                      disabled: !form.schedule || !form.prompt, onClick: create },
          "＋ ny Hermes-jobb")));
  }

  function FleetSection() {
    const { data, err } = useData("/api/plugins/fleetcron/fleet", 0);
    const byHost = useMemo(() => {
      const out = {};
      ((data && data.jobs) || []).forEach((j) => {
        (out[j.host] = out[j.host] || []).push(j);
      });
      return out;
    }, [data]);
    if (err) return h("div", { className: "fc-err" }, "flåte-registeret utilgjengelig: " + err);
    return h("div", null, Object.keys(byHost).sort().map((host) =>
      h("div", { key: host, className: "fc-section" },
        h("h3", { className: "fc-h" }, HOST_LABELS[host] || host, " ",
          h("span", { className: "fc-dim" }, "(" + byHost[host].length + " jobber — eies av maskinen; samlet av kollektoren)")),
        h("table", { className: "fc-table" },
          h("thead", null, h("tr", null, ["jobb", "scheduler", "schedule", "kommando"]
            .map((c) => h("th", { key: c }, c)))),
          h("tbody", null, byHost[host].map((j, i) =>
            h("tr", { key: host + i, className: "fc-row" },
              h("td", { className: "fc-name" }, j.label || "—"),
              h("td", null, j.scheduler),
              h("td", { className: "fc-sched" }, j.schedule),
              h("td", { className: "fc-cmd", title: j.command }, (j.command || "").slice(0, 90))))))
      )));
  }

  function FleetCronPage() {
    const [msg, setMsg] = useState(null);
    const { data: fleet } = useData("/api/plugins/fleetcron/fleet", 0);
    const n = ((fleet && fleet.jobs) || []).length;
    return h("div", { className: "fc-wrap" },
      h("div", { className: "fc-header" },
        h("h2", null, "Cron — hele symbiosen"),
        h("p", { className: "fc-sub" },
          "Alt som kjører på klokke, ett brett: Hermes-jobbene forvaltes her; "
          + "flåten (.11/.12/.13) samles automatisk av fleet_cron_collector hver time — "
          + "nye cron/launchd-jobber dukker opp av seg selv.")),
      msg && h("div", { className: "fc-msg", onClick: () => setMsg(null) }, msg),
      h("div", { className: "fc-stats" },
        h(Card, null, h(CardContent, { className: "fc-stat" },
          h("div", { className: "fc-stat-n" }, String(n)),
          h("div", { className: "fc-stat-l" }, "flåte-jobber i grafen")))),
      h(HermesJobs, { setMsg }),
      h(FleetSection, null));
  }

  if (window.__HERMES_PLUGINS__ && typeof window.__HERMES_PLUGINS__.register === "function") {
    window.__HERMES_PLUGINS__.register("fleetcron", FleetCronPage);
  }
})();
