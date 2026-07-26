// DomainPage — NATIVE domene-fane (BL-2336, bølge 1 av «alt over native, ikke speil»).
//
// Én side, syv domener: strukturert JSON fra opus_domain_snapshot (samme cfg-
// spørringer som dashbordet — én sannhetskilde), rendret rent i Hermes-idiomet.
// Ingen sanitert-HTML-innbygging, ingen scoped-CSS-oversettelse — ekte native.
//
// Sparkline tegnes som inline-SVG med currentColor — arver tema, null deps.

import { useEffect, useState } from "react";

import { fetchJSON } from "@/lib/api";
import { PANEL, SECTION_LABEL, toneBadge } from "@/pages/symbioseTheme";

type Pill = { label: string; value: unknown; tone: string; blind: boolean };
type Table = { cols: string[]; rows: unknown[][]; total?: number } | null;
type Section = { title: string; table: Table };
type Domain = {
  title: string;
  bl: string;
  source_note: string;
  daily_source: string;
  pills: Pill[];
  series: number[];
  findings: Table;
  couplings: Table;
  extra_title: string;
  // BL-2551: de rike domene-seksjonene (cfg.extra_tables) — cyber's ~31 EDR-paneler
  // (beaconing/exfil/scan/lateral/wildfire/threat-intel/wazuh …). Tom for domener
  // uten extra_tables. `trends` = L6 temporale trender (paritet med :8910-kilden).
  sections?: Section[];
  trends?: Table;
};
// BL-2369: :IngestSourceSpec-registeret rir på samme snapshot (opus_domain_
// snapshot henter det via unified-APIets read-only GET på .13). Domener uten
// snapshot-generator rendres fra denne blokka — kildeliste + migreringsstatus.
type RegSpec = {
  name?: string;
  kind?: string;
  migration?: string;
  consumer?: string;
  container?: string;
  updated?: string;
};
type Register = {
  blind?: boolean;
  grunn?: string;
  count?: number;
  truncated?: boolean;
  domains?: Record<string, RegSpec[]>;
};
type Payload = {
  available: boolean;
  reason?: string;
  generated_at?: string | null;
  domains?: Record<string, Domain>;
  register?: Register;
};

// jetstream-livssyklusen (BL-2356/2358): proposed → shadow → active; legacy_daemon
// = kjører via gammel container, retired = bevisst avviklet. Tonene følger det.
const MIG_TONE: Record<string, string> = {
  active: "green",
  shadow: "amber",
  proposed: "blue",
  legacy_daemon: "grey",
  retired: "grey",
};

function Sparkline({ data }: { data: number[] }) {
  if (data.length < 2) return null;
  const w = 280;
  const h = 40;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const span = max - min || 1;
  const pts = data
    .map((v, i) => `${((i / (data.length - 1)) * w).toFixed(1)},${(h - ((v - min) / span) * (h - 4) - 2).toFixed(1)}`)
    .join(" ");
  return (
    <svg width={w} height={h} className="text-primary" aria-hidden>
      <polyline points={pts} fill="none" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}

function DataTable({ t, title }: { t: Table; title: string }) {
  if (t === null)
    return (
      <div className={`${PANEL} p-3 text-sm text-warning`}>
        {title}: spørringen feilet (BLIND) — betyr ikke «ingen funn».
      </div>
    );
  if (!t.rows.length)
    return <div className={`${PANEL} p-3 text-sm text-muted-foreground`}>{title}: ingen rader ✓</div>;
  return (
    <div className={`${PANEL} overflow-x-auto`}>
      <table className="w-full text-sm">
        <thead className="bg-muted/20 text-left text-xs text-muted-foreground">
          <tr>
            {t.cols.map((c) => (
              <th key={c} className="px-3 py-2 font-medium">{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {t.rows.map((r, i) => (
            <tr key={i} className="border-t border-border/60 hover:bg-muted/20">
              {r.map((c, j) => (
                <td key={j} className="max-w-[26rem] truncate px-3 py-1.5 font-mono text-[0.6875rem] text-muted-foreground">
                  {String(c ?? "—")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {(t.total ?? t.rows.length) > t.rows.length && (
        <div className="border-t border-border/60 px-3 py-1.5 text-xs text-muted-foreground">
          viser {t.rows.length} av {t.total}
        </div>
      )}
    </div>
  );
}

// BL-2551: pent + oversiktlig gruppering av de rike domene-seksjonene (cyber's
// ~31 EDR-paneler). Data-bærende deteksjoner som fulle tabeller (mest interessant
// øverst); BLIND-spørringer flagges ærlig; dvalende (0 funn) samles kompakt som
// chips — aldri skjult (honesty-regimet), men aldri en vegg av tomme tabeller.
function shortTitle(t: string): string {
  const dash = t.indexOf(" — ");
  const s = dash > 0 ? t.slice(0, dash) : t;
  return s.length > 46 ? `${s.slice(0, 46)}…` : s;
}

function EdrSections({ sections, groupTitle }: { sections: Section[]; groupTitle: string }) {
  const withData = sections.filter((s) => s.table && s.table.rows.length > 0);
  const blind = sections.filter((s) => s.table === null);
  const dormant = sections.filter((s) => s.table && s.table.rows.length === 0);
  return (
    <section className="flex flex-col gap-4">
      <div className={SECTION_LABEL}>
        {(groupTitle || "Deteksjons-paneler").toUpperCase()}
        <span className="ml-2 font-normal text-muted-foreground">
          {withData.length} aktive · {dormant.length} dvalende
          {blind.length ? ` · ${blind.length} blind` : ""}
        </span>
      </div>
      {withData.map((s, i) => (
        <div key={`d${i}`} className="flex flex-col gap-1.5">
          <div className="text-sm font-medium text-foreground">{s.title}</div>
          <DataTable t={s.table} title={s.title} />
        </div>
      ))}
      {blind.map((s, i) => (
        <div key={`b${i}`} className={`${PANEL} p-2.5 text-xs text-warning`}>
          ⚠ {shortTitle(s.title)}: spørringen feilet (BLIND) — ikke «ingen funn».
        </div>
      ))}
      {dormant.length > 0 && (
        <div className={`${PANEL} p-3`}>
          <div className="mb-2 text-xs text-muted-foreground">
            Dvalende detektorer — 0 funn ({dormant.length}), struktur vist ærlig:
          </div>
          <div className="flex flex-wrap gap-1.5">
            {dormant.map((s, i) => (
              <span
                key={`z${i}`}
                className="border border-border/60 px-1.5 py-0.5 text-[0.6875rem] text-muted-foreground"
                title={s.title}
              >
                {shortTitle(s.title)}
              </span>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

// Generisk fallback (BL-2369): domenet finnes i kilderegisteret men har ingen
// snapshot-generator ennå — vis kildelista + migreringsstatus i stedet for bare
// «ikke speilet». Ærlighet: register-BLIND sies eksplisitt, kapp aldri stille.
function RegisterFallback({ domain, data }: { domain: string; data: Payload }) {
  const reg = data.register;
  const specs = reg?.domains?.[domain];
  if (!specs?.length)
    return (
      <div className="p-6">
        <div className={`${PANEL} p-4 text-sm`}>
          <div className="font-medium text-warning">Snapshotet er ikke speilet ennå</div>
          <div className="mt-1 text-muted-foreground">{data.reason ?? `domene '${domain}' mangler`}</div>
          {reg?.blind && (
            <div className="mt-1 text-warning">
              kilderegisteret er BLIND ({reg.grunn ?? "ukjent"}) — domenet kan ha kilder uten at vi ser dem.
            </div>
          )}
        </div>
      </div>
    );

  const byStatus: Record<string, number> = {};
  for (const s of specs) {
    const k = s.migration ?? "ukjent";
    byStatus[k] = (byStatus[k] ?? 0) + 1;
  }
  return (
    <div className="flex flex-col gap-5 p-4">
      <div>
        <div className={SECTION_LABEL}>{domain.toUpperCase()} — KILDEREGISTER</div>
        <p className="mt-1 text-xs text-muted-foreground">
          graf-drevet fane (:IngestSourceSpec): domenet har ingen snapshot-generator ennå —
          viser kildeliste + migreringsstatus · speilet{" "}
          <span className="font-mono">{data.generated_at?.slice(0, 19) ?? "—"}</span>
        </p>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {Object.entries(byStatus).map(([k, n]) => (
          <span key={k} className={`border px-2 py-1 text-xs ${toneBadge(MIG_TONE[k] ?? "grey")}`}>
            {k}: <span className="font-mono">{n}</span>
          </span>
        ))}
        {reg?.truncated && (
          <span className="px-2 py-1 text-xs text-warning">
            registeret er kappet ved 500 kilder — lista kan mangle innslag
          </span>
        )}
      </div>

      <section>
        <div className={`${SECTION_LABEL} mb-2`}>KILDER</div>
        <DataTable
          title="kilder"
          t={{
            cols: ["kilde", "type", "migrering", "consumer", "container", "oppdatert"],
            rows: specs.map((s) => [s.name, s.kind, s.migration, s.consumer, s.container, s.updated]),
          }}
        />
      </section>
    </div>
  );
}

export default function DomainPage({ domain }: { domain: string }) {
  const [data, setData] = useState<Payload | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setData(null);
    fetchJSON<Payload>("/api/symbiose/domains")
      .then(setData)
      .catch((e) => setErr(String(e)));
  }, [domain]);

  if (err) return <div className="p-6 text-sm text-warning">Kunne ikke hente domenet: {err}</div>;
  if (!data) return <div className="p-6 text-sm text-muted-foreground">Henter {domain} …</div>;
  const d = data.domains?.[domain];
  // BL-2369: mangler domenet i snapshotet, kan det likevel finnes i kilde-
  // registeret (jetstream promoterer autonomt) — RegisterFallback viser da
  // kildelista, og faller ellers tilbake til den gamle «ikke speilet»-meldingen.
  if (!data.available || !d) return <RegisterFallback domain={domain} data={data} />;

  return (
    <div className="flex flex-col gap-5 p-4">
      <div>
        <div className={SECTION_LABEL}>{d.title.toUpperCase()}</div>
        <p className="mt-1 text-xs text-muted-foreground">
          {d.source_note} {d.bl ? `· ${d.bl}` : ""} · speilet{" "}
          <span className="font-mono">{data.generated_at?.slice(0, 19) ?? "—"}</span>
        </p>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {d.pills.slice(0, 14).map((p) => (
          <span
            key={p.label}
            className={`border px-2 py-1 text-xs ${p.blind ? toneBadge("grey") : toneBadge(p.tone)}`}
            title={p.label}
          >
            {p.label}:{" "}
            <span className="font-mono">{p.blind ? "BLIND" : String(p.value ?? "—")}</span>
          </span>
        ))}
        {d.pills.length > 14 && (
          <span className="px-2 py-1 text-xs text-muted-foreground">+{d.pills.length - 14} til</span>
        )}
      </div>

      {d.series.length > 1 && (
        <div className={`${PANEL} p-3`}>
          <div className="mb-1 text-xs text-muted-foreground">
            signalserie <span className="font-mono">{d.daily_source}</span>
          </div>
          <Sparkline data={d.series} />
        </div>
      )}

      <section>
        <div className={`${SECTION_LABEL} mb-2`}>FUNN</div>
        <DataTable t={d.findings} title="funn" />
      </section>

      <section>
        <div className={`${SECTION_LABEL} mb-2`}>
          {((d.sections?.length ? "Selskaps-koblinger" : d.extra_title) || "Koblinger").toUpperCase()}
        </div>
        <DataTable t={d.couplings} title="koblinger" />
      </section>

      {d.trends && d.trends.rows.length > 0 && (
        <section>
          <div className={`${SECTION_LABEL} mb-2`}>TEMPORALE TRENDER</div>
          <DataTable t={d.trends} title="trender" />
        </section>
      )}

      {d.sections && d.sections.length > 0 && (
        <EdrSections sections={d.sections} groupTitle={d.extra_title} />
      )}
    </div>
  );
}
