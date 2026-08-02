/**
 * Brukere — chat-plattformens bruker-administrasjon (BL-2653). NATIVE: Nous
 * DS-komponentene fra plugin-SDK-en (Card/Badge/Button) + Hermes' tailwind-
 * klasser, samme mønster som Tilgang-fanen (style.css er tom med vilje).
 *
 * Multiuser-planens første synlige flate (charter
 * plan:symbiose_multiuser_chat_platform): Morten er første bruker (admin) og
 * legger inn de neste selv. Butikken er users.json i HERMES_HOME; innloggings-
 * veien er dashboard_auth/local_users (aktiveres når dashboardet bindes gated
 * — i loopback-modus i dag er fanen ren administrasjon).
 */
(function () {
  "use strict";

  const SDK = window.__HERMES_PLUGIN_SDK__;
  if (!SDK) return;
  const { React } = SDK;
  const h = React.createElement;
  const { Card, CardHeader, CardTitle, CardContent, Badge, Button } = SDK.components;
  const { useState, useEffect } = SDK.hooks;

  const API = "/api/plugins/brukere";
  const jfetch = (path, opts) =>
    SDK.fetchJSON ? SDK.fetchJSON(API + path, opts)
      : SDK.authedFetch ? SDK.authedFetch(API + path, opts).then((r) => r.json())
      : fetch(API + path, opts).then((r) => r.json());
  const jsonOpts = (method, body) => ({
    method: method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  const INPUT = "w-full border border-border bg-background/40 px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground";
  const TD = "py-1.5 pr-3 align-top";
  const GRID = { display: "grid", gap: "0.5rem", gridTemplateColumns: "repeat(auto-fill, minmax(155px, 1fr))" };

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

  function Field(label, input) {
    return h("label", { className: "block" },
      h("span", { className: "block text-[0.6875rem] uppercase tracking-wide text-muted-foreground mb-1" }, label),
      input);
  }

  // Skjema for å opprette bruker. Gjenbrukes av bootstrap («deg selv først»)
  // og vanlig «legg til bruker» — kun tekstene skiller.
  function UserForm(props) {
    const bootstrap = !!props.bootstrap;
    const [username, setUsername] = useState("");
    const [displayName, setDisplayName] = useState("");
    const [email, setEmail] = useState("");
    const [role, setRole] = useState(bootstrap ? "admin" : "user");
    const [password, setPassword] = useState("");
    const [generate, setGenerate] = useState(!bootstrap);
    const [totp, setTotp] = useState(!bootstrap);
    const [busy, setBusy] = useState(false);
    const [msg, setMsg] = useState(null);

    const submit = () => {
      if (!username || (!generate && (password || "").length < 8)) {
        setMsg({ tone: "err", text: "brukernavn kreves; passord minst 8 tegn (eller generer)" });
        return;
      }
      setBusy(true);
      jfetch("/users", jsonOpts("POST", {
        username: username, display_name: displayName, email: email,
        role: bootstrap ? "admin" : role,
        password: generate ? null : password,
        totp: bootstrap ? false : totp,
      })).then((r) => {
        if (r && r.detail) { setMsg({ tone: "err", text: String(r.detail) }); return; }
        const bits = ["opprettet: " + username];
        if (r && r.generated_password) bits.push("engangspassord (vises KUN nå): " + r.generated_password);
        if (r && r.totp_secret) bits.push("2FA-secret til authenticator (vises KUN nå): " + r.totp_secret + " — otpauth-URI: " + r.otpauth_uri);
        setMsg({ tone: "ok", text: bits.join(" · ") });
        setUsername(""); setDisplayName(""); setEmail(""); setPassword("");
        if (props.onDone) props.onDone();
      }).catch((e) => setMsg({ tone: "err", text: String(e) }))
        .finally(() => setBusy(false));
    };

    return h("div", { className: "space-y-3 max-w-xl" },
      h("div", { className: "grid gap-3 sm:grid-cols-2" },
        Field("brukernavn", h("input", { className: INPUT, value: username,
          placeholder: bootstrap ? "morten" : "fornavn", autoComplete: "off",
          onChange: (e) => setUsername(e.target.value.toLowerCase()) })),
        Field("visningsnavn", h("input", { className: INPUT, value: displayName,
          placeholder: "Vises i chatten", onChange: (e) => setDisplayName(e.target.value) })),
        Field("e-post (valgfri)", h("input", { className: INPUT, value: email,
          placeholder: "navn@…", autoComplete: "off", onChange: (e) => setEmail(e.target.value) })),
        bootstrap ? null : Field("rolle",
          h("select", { className: INPUT, value: role, onChange: (e) => setRole(e.target.value) },
            h("option", { value: "user" }, "bruker"),
            h("option", { value: "admin" }, "admin")))),
      h("div", { className: "flex flex-wrap items-end gap-3" },
        h("label", { className: "inline-flex items-center gap-2 text-sm text-muted-foreground" },
          h("input", { type: "checkbox", checked: generate,
            onChange: (e) => setGenerate(e.target.checked) }),
          "generer engangspassord"),
        bootstrap ? null : h("label", { className: "inline-flex items-center gap-2 text-sm text-muted-foreground" },
          h("input", { type: "checkbox", checked: totp,
            onChange: (e) => setTotp(e.target.checked) }),
          "2FA (authenticator) — anbefalt for internett-flaten"),
        generate ? null : h("div", { className: "grow max-w-xs" },
          Field("passord (minst 8 tegn)", h("input", { className: INPUT, type: "password",
            value: password, autoComplete: "new-password",
            onChange: (e) => setPassword(e.target.value) }))),
        h(Button, { onClick: submit, disabled: busy },
          bootstrap ? "Opprett meg som admin" : "Legg til bruker")),
      msg ? h("p", { className: "text-sm " + (msg.tone === "ok" ? "text-emerald-500" : "text-destructive") },
        msg.text) : null,
      bootstrap ? h("p", { className: "text-xs text-muted-foreground" },
        "Første bruker blir alltid admin — det er deg. Passordet hashes (scrypt) og lagres aldri i klartekst.") : null);
  }

  function UserRow(props) {
    const u = props.user;
    const [busy, setBusy] = useState(false);
    const [pwMsg, setPwMsg] = useState(null);
    const patch = (body) => {
      setBusy(true);
      jfetch("/users/" + encodeURIComponent(u.username), jsonOpts("PATCH", body))
        .then((r) => {
          if (r && r.detail) setPwMsg(String(r.detail));
          props.onChanged();
        })
        .catch((e) => setPwMsg(String(e)))
        .finally(() => setBusy(false));
    };
    const resetPw = () => {
      setBusy(true);
      jfetch("/users/" + encodeURIComponent(u.username) + "/password", jsonOpts("POST", {}))
        .then((r) => setPwMsg(r && r.generated_password
          ? "nytt engangspassord (vises KUN nå): " + r.generated_password
          : (r && r.detail ? String(r.detail) : "ok")))
        .catch((e) => setPwMsg(String(e)))
        .finally(() => setBusy(false));
    };
    const toggleTotp = () => {
      setBusy(true);
      jfetch("/users/" + encodeURIComponent(u.username) + "/totp", jsonOpts("POST", { enable: !u.has_totp }))
        .then((r) => {
          if (r && r.totp_secret) setPwMsg("2FA PÅ — secret til authenticator (vises KUN nå): " + r.totp_secret + " — otpauth-URI: " + r.otpauth_uri);
          else if (r && r.detail) setPwMsg(String(r.detail));
          else setPwMsg("2FA av");
          props.onChanged();
        })
        .catch((e) => setPwMsg(String(e)))
        .finally(() => setBusy(false));
    };
    const btn = "px-2 py-1 text-xs";
    return h(React.Fragment, null,
      h("tr", { className: "border-t border-border/60" },
        h("td", { className: TD + " font-medium whitespace-nowrap" }, u.username),
        h("td", { className: TD }, u.display_name || ""),
        h("td", { className: TD + " text-muted-foreground" }, u.email || ""),
        h("td", { className: TD }, h(Badge, {
          tone: u.role === "admin" ? "success" : "secondary", className: "text-xs" }, u.role)),
        h("td", { className: TD }, h(Badge, {
          tone: u.disabled ? "destructive" : "success", className: "text-xs" },
          u.disabled ? "deaktivert" : "aktiv")),
        h("td", { className: TD }, h(Badge, {
          tone: u.has_totp ? "success" : "outline", className: "text-xs" },
          u.has_totp ? "2FA på" : "2FA av")),
        h("td", { className: TD + " text-muted-foreground whitespace-nowrap text-xs" },
          u.last_login || "aldri"),
        h("td", { className: TD },
          h("div", { className: "flex flex-wrap gap-1.5" },
            h(Button, { ghost: true, className: btn, disabled: busy,
              onClick: () => patch({ disabled: !u.disabled }) },
              u.disabled ? "aktiver" : "deaktiver"),
            h(Button, { ghost: true, className: btn, disabled: busy,
              onClick: () => patch({ role: u.role === "admin" ? "user" : "admin" }) },
              u.role === "admin" ? "gjør til bruker" : "gjør til admin"),
            h(Button, { ghost: true, className: btn, disabled: busy, onClick: resetPw },
              "nytt passord"),
            h(Button, { ghost: true, className: btn, disabled: busy, onClick: toggleTotp },
              u.has_totp ? "2FA av" : "2FA på")))),
      pwMsg ? h("tr", null, h("td", { colSpan: 8,
        className: "py-1 pr-3 text-xs " + (pwMsg.indexOf("passord") >= 0 ? "text-emerald-500" : "text-destructive") },
        pwMsg)) : null);
  }

  // BL-3404: søknad fra registreringsskjemaet på ai.byopus.com. Du godkjenner
  // PERSONEN — 2FA-secreten ser du aldri: den går til søkerens egen
  // authenticator ved første innlogging, og uten den kommer de ikke inn.
  function PendingRow(props) {
    const p = props.item;
    const [busy, setBusy] = useState(false);
    const [msg, setMsg] = useState(null);
    const [role, setRole] = useState("user");
    const [att, setAtt] = useState(0);
    const act = (what, body) => {
      setBusy(true);
      jfetch("/pending/" + encodeURIComponent(p.id) + "/" + what, jsonOpts("POST", body || {}))
        .then((r) => {
          if (r && r.detail) { setMsg(String(r.detail)); return; }
          props.onChanged();
        })
        .catch((e) => setMsg(String(e)))
        .finally(() => setBusy(false));
    };
    const btn = "px-2 py-1 text-xs";
    return h(React.Fragment, null,
      h("tr", { className: "border-t border-border/60" },
        h("td", { className: TD + " font-medium whitespace-nowrap" }, p.username),
        h("td", { className: TD }, p.display_name || ""),
        h("td", { className: TD + " text-muted-foreground" }, p.email || ""),
        h("td", { className: TD + " text-muted-foreground whitespace-nowrap text-xs" }, p.created_at || ""),
        h("td", { className: TD + " text-muted-foreground whitespace-nowrap text-xs" }, p.source_ip || ""),
        h("td", { className: TD },
          p.collision
            ? h(Badge, { tone: "destructive", className: "text-xs" }, "navn opptatt")
            : h("select", { className: INPUT + " !py-1 !text-xs", value: role,
                onChange: (e) => setRole(e.target.value) },
                h("option", { value: "user" }, "bruker"),
                h("option", { value: "admin" }, "admin"))),
        h("td", { className: TD },
          h("div", { className: "flex flex-wrap gap-1.5" },
            h(Button, { className: btn, disabled: busy || p.collision,
              onClick: () => act("approve", { role: role, attempt: att }) }, "godkjenn"),
            h(Button, { ghost: true, className: btn, disabled: busy,
              onClick: () => act("reject", {}) }, "avslå")))),
      // Gjentatte innsendinger for SAMME brukernavn: kan være søkeren som
      // prøvde igjen — eller noen som forsøkte å kapre søknaden. Den første
      // innsendingen er den som gjelder (passordet under er søkerens eget),
      // men du skal se at det skjedde før du godkjenner.
      (p.attempts || []).length > 1 ? h("tr", null, h("td", { colSpan: 7,
        className: "py-1.5 pr-3 text-xs" },
        h("div", { className: "text-amber-500 mb-1.5" },
          "⚠ skjemaet er sendt inn " + (p.resubmit_count + 1) + " ganger for dette brukernavnet" +
          // attempts[] stopper på ATTEMPTS_MAX, resubmit_count gjør ikke det.
          // Uten dette så 500 kapringsforsøk identisk ut med 4 ærlige (F5).
          (p.resubmit_count + 1 > p.attempts.length
            ? " (de " + p.attempts.length + " første er bevart under — resten ble forkastet)" : "") + ". " +
          "Nr. 1 er standard — velg en senere KUN hvis søkeren har sagt at de måtte gjøre det om igjen " +
          "(f.eks. mistet telefonen). Ellers kan det være noen andre som prøver å overta navnet."),
        h("div", { className: "flex flex-wrap gap-3" },
          p.attempts.map((a, i) => h("label", { key: i,
            className: "inline-flex items-center gap-1.5 text-muted-foreground" },
            h("input", { type: "radio", name: "att-" + p.id, checked: att === i,
              onChange: () => setAtt(i) }),
            "nr. " + (i + 1) + " · " + (a.at || "") + (a.ip ? " · " + a.ip : "")))))) : null,
      msg ? h("tr", null, h("td", { colSpan: 7, className: "py-1 pr-3 text-xs text-destructive" }, msg)) : null);
  }


  // ── BL-3428 / ADR-046: kapabilitets-styring ──────────────────────────────
  // Morten: «admin skal ha alt, og user skal jeg kunne sette en og en på.»
  // Derfor ÉN tabell: rad = kategori, kolonne = hvem. Admin-kolonnen er låst
  // (rollen ER tilgangen), «alle» gjelder også FRAMTIDIGE brukere, og hver
  // bruker har sin egen avkrysning. Ingen «klassifisering» å oversette i hodet.
  //
  // Under panseret er dette de samme to feltene som før — «alle» skriver
  // policyens kategori=system, en enkelt avkrysning skriver brukerens
  // granted_capabilities — men det er en implementasjonsdetalj Morten ikke
  // skal måtte kjenne for å styre tilgang.
  function Kapabiliteter(props) {
    const users = (props.users || []).filter((u) => u.role !== "admin" && !u.disabled);
    const [data, setData] = useState(null);
    const [busy, setBusy] = useState(false);
    const [msg, setMsg] = useState(null);
    const [alle, setAlle] = useState({});     // kategori -> alle brukere
    const [gitt, setGitt] = useState({});     // brukernavn -> [kategorier]

    const load = () => jfetch("/capabilities").then((d) => {
      setData(d);
      const a = {};
      (d.categories || []).forEach((c) => {
        a[c.category] = (c.classification || c.effective_default) === "system";
      });
      setAlle(a);
      const g = {};
      (props.users || []).forEach((u) => { g[u.username] = (u.granted_capabilities || []).slice(); });
      setGitt(g);
    }).catch((e) => setMsg(String(e)));
    useEffect(() => { load(); }, [props.tick]);

    if (!data) return h("p", { className: "text-sm text-muted-foreground" }, "laster …");
    const cats = data.categories || [];
    const et = data.enforced_tree || {};

    const harBruker = (u, cat) => (gitt[u] || []).indexOf(cat) >= 0;
    const toggleBruker = (u, cat) => setGitt(Object.assign({}, gitt, {
      [u]: harBruker(u, cat) ? (gitt[u] || []).filter((x) => x !== cat)
                             : (gitt[u] || []).concat([cat]) }));

    const lagre = () => {
      setBusy(true); setMsg(null);
      const pol = {};
      cats.forEach((c) => { pol[c.category] = alle[c.category] ? "system" : "owner"; });
      jfetch("/capabilities/policy", jsonOpts("POST", { categories: pol }))
        .then(() => Promise.all((props.users || []).map((u) =>
          jfetch("/users/" + encodeURIComponent(u.username) + "/capabilities",
                 jsonOpts("POST", { granted: gitt[u.username] || [] })))))
        .then(() => { setMsg("lagret"); load(); if (props.onChanged) props.onChanged(); })
        .catch((e) => setMsg(String(e)))
        .finally(() => setBusy(false));
    };

    const cb = (checked, onChange, disabled) => h("input", {
      type: "checkbox", checked: checked, disabled: !!disabled, onChange: onChange });

    return h("div", { className: "space-y-3" },
      et.ok && (et.kun_i_admin || []).length + (et.kun_i_runtime || []).length > 0
        ? h("div", { className: "border border-amber-600/40 bg-amber-500/5 px-3 py-2 text-xs space-y-1" },
            h("div", { className: "text-amber-500 font-medium" },
              "De to Hermes-hjemmene har ulike skill-tre — denne flaten viser " +
              data.total_skills + ", gaten håndhever " + et.skills + "."),
            (et.kun_i_admin || []).length
              ? h("div", { className: "text-muted-foreground" },
                  "Vises her, men håndheves ALDRI: " + et.kun_i_admin.join(", ")) : null,
            (et.kun_i_runtime || []).length
              ? h("div", { className: "text-muted-foreground" },
                  "Håndheves, men vises ikke her (blir skjult for vanlige brukere): " +
                  et.kun_i_runtime.join(", ")) : null)
        : null,
      users.length === 0
        ? h("p", { className: "text-xs text-muted-foreground" },
            "Du er eneste bruker, og admin ser alt. Kolonnene til høyre fylles ut " +
            "når du legger til en bruker — eller godkjenner en søknad. Kryss av " +
            "«alle brukere» nå for å bestemme hva de får fra dag én.")
        : null,
      h("div", { className: "overflow-x-auto" },
        h("table", { className: "w-full text-sm" },
          h("thead", null,
            h("tr", { className: "border-b border-border" },
              // ADMIN-kolonna er fjernet (Morten: «bare med user»). Den var
              // alltid ✓ og aldri klikkbar — en kolonne som bærer null
              // informasjon er støy i en tabell som skal tas beslutninger i.
              // At admin ser alt står i teksten over, én gang.
              ["kategori", "skills", "alle"].concat(users.map((u) => u.username))
                .map((c, i) => h("th", { key: c,
                  className: "text-left font-medium text-[0.6875rem] uppercase tracking-wider text-muted-foreground py-2 pr-3" +
                    (i >= 2 ? " text-center" : "") }, c)))),
          h("tbody", null, cats.map((c) => {
            const erklaert = Object.keys(c.declared || {}).length;
            return h("tr", { key: c.category, className: "border-t border-border/60" },
              h("td", { className: TD + " whitespace-nowrap" },
                h("span", { className: "font-medium" }, c.category),
                c.symbiose_owned
                  ? h(Badge, { tone: "destructive", className: "ml-2 text-xs" }, "Symbiose")
                  : null,
                erklaert
                  ? h("span", { className: "ml-2 text-xs text-muted-foreground" },
                      "(" + erklaert + " styrer seg selv)")
                  : null),
              h("td", { className: TD + " tabular-nums" }, c.count),
              h("td", { className: TD + " text-center" },
                cb(!!alle[c.category], () => setAlle(Object.assign({}, alle,
                  { [c.category]: !alle[c.category] })))),
              users.map((u) => h("td", { key: u.username, className: TD + " text-center" },
                cb(alle[c.category] || harBruker(u.username, c.category),
                   () => toggleBruker(u.username, c.category),
                   alle[c.category]))));
          })))),
      h("div", { className: "flex flex-wrap items-center gap-3" },
        h(Button, { onClick: lagre, disabled: busy }, "Lagre tilganger"),
        users.length
          ? h(React.Fragment, null,
              h(Button, { ghost: true, className: "px-2 py-1 text-xs", disabled: busy,
                onClick: () => { const g = {}; users.forEach((u) => { g[u.username] = cats.map((c) => c.category); });
                                 setGitt(Object.assign({}, gitt, g)); } },
                "Gi alle brukere alt (lik admin)"),
              h(Button, { ghost: true, className: "px-2 py-1 text-xs", disabled: busy,
                onClick: () => { const g = {}; users.forEach((u) => { g[u.username] = []; });
                                 setGitt(Object.assign({}, gitt, g)); setAlle({}); } },
                "Nullstill alt"))
          : null,
        msg ? h("span", { className: "text-sm text-muted-foreground" }, msg) : null),
      h("p", { className: "text-xs text-muted-foreground" },
        "«Alle» gjelder også brukere du legger til senere. En enkelt avkrysning " +
        "gjelder bare den brukeren. Uten noen avkrysning ser kun admin kategorien — " +
        "det er med vilje (ADR-045 D2): «vi rakk ikke å bestemme» skal aldri bety " +
        "«alle ser den». En skill som styrer seg selv i sin egen SKILL.md overstyrer raden."));
  }

  function BrukerePage() {
    const [tick, setTick] = useState(0);
    const [status, setStatus] = useState(null);
    const [users, setUsers] = useState(null);
    const [pending, setPending] = useState(null);
    const [capData, setCapData] = useState(null);
    const [err, setErr] = useState(null);
    const reload = () => setTick((t) => t + 1);

    useEffect(() => {
      let alive = true;
      jfetch("/status").then((s) => {
        if (!alive) return;
        setStatus(s); setErr(null);
        if (!s.bootstrap_required) {
          jfetch("/users").then((d) => alive && setUsers((d && d.users) || []))
            .catch((e) => alive && setErr(String(e)));
          jfetch("/pending").then((d) => alive && setPending((d && d.pending) || []))
            .catch(() => alive && setPending([]));
          jfetch("/capabilities").then((d) => alive && setCapData(d)).catch(() => alive && setCapData(null));
        } else {
          setUsers([]); setPending([]);
        }
      }).catch((e) => alive && setErr(String(e)));
      return () => { alive = false; };
    }, [tick]);

    if (err) {
      return h("div", { className: "p-4" },
        Section({ title: "Brukere" },
          h("p", { className: "text-sm text-destructive" }, "utilgjengelig: " + err)));
    }
    if (!status) {
      return h("div", { className: "p-4" },
        Section({ title: "Brukere" },
          h("p", { className: "text-sm text-muted-foreground" }, "laster …")));
    }

    const sections = [];

    sections.push(Section({ title: "Chat-plattformens brukere",
      sub: "butikk: " + status.store_path + " — innloggingsvei: dashboard_auth/local_users" },
      h("div", { style: GRID },
        tile(status.user_count, "brukere"),
        tile(status.active_count, "aktive"),
        tile(status.admin_count, "admin"),
        tile(status.pending_count != null ? status.pending_count : 0, "søknader"),
        tile(status.gate_active ? "på" : "av (loopback)", "innloggings-gate"))));

    if (!status.bootstrap_required) {
      const open = pending || [];
      sections.push(Section({
        title: "Søknader om tilgang", badge: open.length,
        badgeTone: open.length ? "destructive" : "outline",
        sub: "Sendt fra «Registrer deg» på ai.byopus.com. Søkeren koblet på authenticator ALLEREDE i skjemaet og beviste det med en gyldig kode — en søknad som står her er ferdig 2FA-sikret. Nøkkelen bor i deres app, aldri her." },
        pending === null
          ? h("p", { className: "text-sm text-muted-foreground" }, "laster …")
          : open.length === 0
            ? h("p", { className: "text-sm text-muted-foreground" }, "ingen åpne søknader.")
            : Table(["bruker", "navn", "e-post", "søkt", "fra IP", "rolle", ""],
                open.map((p) => h(PendingRow, { key: p.id, item: p, onChanged: reload })))));
    }

    if (status.bootstrap_required) {
      sections.push(Section({ title: "Opprett første bruker (deg)", badgeTone: "outline",
        badge: "bootstrap", sub: "Du er første og eneste bruker — opprett deg selv som admin, så kan du legge inn de neste her." },
        h(UserForm, { bootstrap: true, onDone: reload })));
    } else {
      sections.push(Section({ title: "Brukere", badge: (users || []).length },
        users === null
          ? h("p", { className: "text-sm text-muted-foreground" }, "laster …")
          : Table(["bruker", "navn", "e-post", "rolle", "status", "2fa", "sist innlogget", ""],
              (users || []).map((u) => h(UserRow, { key: u.username, user: u, onChanged: reload })))));
      sections.push(Section({ title: "Legg til bruker",
        sub: "Nye brukere får tilgang til chat-flaten når end-user-skinnet (BL-2464) kobles på; deaktivering dreper levende sesjoner umiddelbart." },
        h(UserForm, { bootstrap: false, onDone: reload })));
    }

    sections.push(Section({ title: "Tilganger — hvem ser hvilke skills",
      badgeTone: "outline", badge: "ADR-046",
      sub: "For hver kategori krysser du av hvilke brukere som skal se den. «Alle» gjelder også dem du legger til senere. Uten avkrysning ser kun admin den — admin ser alltid alt, og det er ikke valgbart." },
      h(Kapabiliteter, { tick: tick, users: users || [], onChanged: reload })));

    sections.push(Section({ title: "Slik virker det", badgeTone: "outline", badge: "BL-2653" },
      h("ul", { className: "list-disc pl-5 space-y-1 text-sm text-muted-foreground" },
        h("li", null, "Butikk: users.json (0600) i HERMES_HOME — scrypt-hash, aldri klartekst; signeringssecret genereres ved første bruker."),
        h("li", null, "Innlogging: login-siden viser «Symbiose-bruker»-skjema når dashboardet bindes med auth-gate; i dag (loopback :9119) er alt bak sesjons-tokenet ditt."),
        h("li", null, "Roller: admin administrerer brukere; bruker chatter. Siste aktive admin kan verken deaktiveres eller degraderes."),
        h("li", null, "Selvregistrering (BL-3404): «Registrer deg» på ai.byopus.com lager en SØKNAD, ikke en konto. Passordet søkeren velger hashes med én gang og lagres aldri i klartekst; skjemaet svarer alltid likt, så det ikke kan brukes til å finne ut hvilke brukernavn som finnes."),
        h("li", null, "2FA er ufravikelig for selvregistrerte: nøkkelen settes opp i selve registreringsskjemaet, og uten en gyldig kode blir det ingen søknad. Du godkjenner en konto som allerede er tofaktor-sikret — og du ser aldri nøkkelen."),
        h("li", null, "Ingen sletting — brukere deaktiveres, søknader avslås (begge står igjen med stempel; husets «vi sletter ingenting»). Et avslag fjerner passord-hashen."),
        h("li", null, "Neste fase (multiuser-planen): per-bruker identitet gjennom adapter/rawmaterial og datalags-scoping (BL-2466) — A7-remodellering er Morten-gatet (BL-2467)."))));

    return h("div", { className: "p-4 space-y-4" }, sections);
  }

  if (window.__HERMES_PLUGINS__ && typeof window.__HERMES_PLUGINS__.register === "function") {
    window.__HERMES_PLUGINS__.register("brukere", BrukerePage);
  }
})();
