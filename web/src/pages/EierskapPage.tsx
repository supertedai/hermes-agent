// EierskapPage — eierskaps-veven i Opus-GUI-en (BL-2328).
//
// Morten: «en agent som har ansvaret for hver enkel fane, hver enkel tile, hver
// enkelte tjeneste … mye glipper». Denne flaten gjør «glipper» til et TALL:
// dekningsprosenten skal opp, ueid-lista skal ned. Hver eier ser porteføljen sin
// med helse-opprulling — eierskap uten synlig plikt er bare maling.

import { useEffect, useState } from "react";

import { fetchJSON } from "@/lib/api";
import { PANEL, SECTION_LABEL, toneBadge, toneText } from "@/pages/symbioseTheme";

type OwnerRow = {
  owner: string;
  surfaces: number;
  tabs: number;
  tiles: number;
  services: number;
  unhealthy: { id: string; health: string }[];
};

type Unowned = { id: string; kind: string; title: string };

type HostRow = {
  host: string;
  total: number;
  owned: number;
  provisional: number;
  reachable: boolean;
  ssh_dark: boolean;
  confirmed_dark: boolean;
  dark_since: string | null;
  unhealthy: { id: string; health: string }[];
};

type Payload = {
  available: boolean;
  reason?: string;
  generated_at?: string | null;
  census?: {
    total: number;
    tabs: number;
    tiles: number;
    services: number;
    owned: number;
    unowned: number;
    coverage_pct: number | null;
    tiles_skipped: string[];
  };
  owners?: OwnerRow[];
  hosts?: HostRow[];
  unowned?: Unowned[];
  operator?: string;
};

function Stat({ label, value, tone }: { label: string; value: string; tone: "grey" | "amber" | "green" }) {
  return (
    <div className={`${PANEL} px-4 py-3`}>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={`mt-0.5 font-mono text-2xl tabular-nums ${tone === "grey" ? "text-foreground" : toneText(tone)}`}>
        {value}
      </div>
    </div>
  );
}

export default function EierskapPage() {
  const [data, setData] = useState<Payload | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    fetchJSON<Payload>("/api/symbiose/ownership")
      .then(setData)
      .catch((e) => setErr(String(e)));
  }, []);

  if (err) return <div className="p-6 text-sm text-warning">Kunne ikke hente eierskap: {err}</div>;
  if (!data) return <div className="p-6 text-sm text-muted-foreground">Henter eierskap …</div>;
  if (!data.available)
    return (
      <div className="p-6">
        <div className={`${PANEL} p-4 text-sm`}>
          <div className="font-medium text-warning">Snapshotet er ikke speilet ennå</div>
          <div className="mt-1 text-muted-foreground">{data.reason}</div>
        </div>
      </div>
    );

  const c = data.census!;
  const cov = c.coverage_pct ?? 0;
  return (
    <div className="flex flex-col gap-5 p-4">
      <p className="text-xs text-muted-foreground">
        Hver fane, hver tile, hver tjeneste — navngitt eier fra agent-rosteret. Census leser
        virkeligheten (hub-registret + speilede tiles + :DaemonState), aldri en håndliste ·
        speilet <span className="font-mono">{data.generated_at?.slice(0, 19) ?? "—"}</span>
      </p>

      <div className="grid gap-2 sm:grid-cols-4">
        <Stat label="flater totalt" value={String(c.total)} tone="grey" />
        <Stat
          label={`${c.tabs} faner · ${c.tiles} tiles · ${c.services} tjenester`}
          value={`${c.owned} eid`}
          tone="grey"
        />
        <Stat label="dekning" value={`${cov}%`} tone={cov >= 95 ? "green" : "amber"} />
        <Stat label="UEID — det som glipper" value={String(c.unowned)} tone={c.unowned ? "amber" : "green"} />
      </div>

      {(data.hosts?.length ?? 0) > 0 && (
        <section>
          <div className={`${SECTION_LABEL} mb-2`}>HOSTS — DEKNING PER MASKIN</div>
          <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-5">
            {data.hosts!.map((h) => {
              const tone: "green" | "amber" =
                h.confirmed_dark || h.ssh_dark || !h.reachable ? "amber" : "green";
              const status = h.confirmed_dark
                ? "MØRK"
                : !h.reachable
                  ? "mørk (blip?)"
                  : h.ssh_dark
                    ? "ssh blokkert"
                    : "oppe";
              return (
                <div key={h.host} className={`${PANEL} p-3`}>
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="font-mono text-sm font-medium">{h.host}</span>
                    <span className={`border px-1.5 py-0.5 font-mono text-[10px] ${toneBadge(tone)}`}>
                      {status}
                    </span>
                  </div>
                  <div className="mt-1 font-mono text-[10px] text-muted-foreground">
                    {h.owned}/{h.total} eid{h.provisional ? ` · ${h.provisional} prov` : ""}
                  </div>
                  {h.confirmed_dark && h.dark_since ? (
                    <div className="mt-1 text-[10px] text-warning">mørk siden {h.dark_since.slice(0, 19)}</div>
                  ) : h.unhealthy.length > 0 ? (
                    <div className={`mt-1 text-[10px] ${toneText("amber")}`}>{h.unhealthy.length} usunne</div>
                  ) : (
                    <div className="mt-1 text-[10px] text-success">svarer</div>
                  )}
                </div>
              );
            })}
          </div>
          <p className="mt-2 text-[11px] text-muted-foreground">
            Grønn = svarer · gul = ssh blokkert (.11 mangler agent-nøkkel) eller mørk · en host som
            slutter å svare (bekreftet, ikke blip) reiser host_dark-forslag til hermes-infra.
          </p>
        </section>
      )}

      <section>
        <div className={`${SECTION_LABEL} mb-2`}>PORTEFØLJER — HVEM SVARER FOR HVA</div>
        <div className="grid gap-2 md:grid-cols-2 lg:grid-cols-3">
          {(data.owners ?? []).map((o) => (
            <div key={o.owner} className={`${PANEL} p-3`}>
              <div className="flex items-baseline justify-between gap-2">
                <span className="text-sm font-medium">{o.owner}</span>
                <span className="font-mono text-[11px] text-muted-foreground">
                  {o.surfaces} flater
                </span>
              </div>
              <div className="mt-0.5 font-mono text-[10px] text-muted-foreground">
                {o.tabs} faner · {o.tiles} tiles · {o.services} tjenester
              </div>
              {o.unhealthy.length > 0 ? (
                <div className="mt-2 border-t border-border/60 pt-1.5">
                  <div className="mb-1 text-[10px] text-warning">
                    plikt nå — {o.unhealthy.length} usunne:
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {o.unhealthy.map((u) => (
                      <span key={u.id} className={`border px-1.5 py-0.5 font-mono text-[10px] ${toneBadge("amber")}`}>
                        {u.id}
                      </span>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="mt-2 border-t border-border/60 pt-1.5 text-[10px] text-success">
                  porteføljen er sunn
                </div>
              )}
            </div>
          ))}
        </div>
        <p className="mt-2 text-[11px] text-muted-foreground">{data.operator}</p>
      </section>

      {(data.unowned?.length ?? 0) > 0 && (
        <section>
          <div className={`${SECTION_LABEL} mb-1`}>UEID ({c.unowned})</div>
          <p className="mb-2 text-xs text-muted-foreground">
            Flater uten navngitt eier — presist det som glipper. Dekningsvakta gate-skriver
            lista; nye regler i opus_ownership.py tar den ned.
          </p>
          <div className="flex flex-wrap gap-1.5">
            {data.unowned!.map((u) => (
              <span
                key={u.id}
                title={u.id}
                className="border border-border px-2 py-0.5 font-mono text-[0.6875rem] text-muted-foreground"
              >
                {u.title}
              </span>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
