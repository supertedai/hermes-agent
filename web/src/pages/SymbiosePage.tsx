// SymbiosePage — agent-flåten i Opus-GUI-en (BL-2290, Morten 2026-07-23).
//
// Morten: «lag en ny fane eller et pent opplegg så viser alle topp agenter, workers osv».
//
// ÆRLIGHETS-REGLENE denne flaten holder (de er hele poenget, ikke pynt):
//   1. success_rate vises ALLTID med n. «100%» av 2 forsøk er ikke det samme som 100% av 200.
//   2. to-lags og ett-lags skilles visuelt. Bare to-lags teller mot opptjent autonomi
//      (grant_recommender filtrerer two_layer=true) — å blande dem ville vist falsk myndighet.
//   3. Agenter uten målt kompetanse listes som nettopp det. Ikke skjult, ikke pyntet.
//   4. Er snapshotet ikke speilet, sier siden DET — den viser aldri «0 agenter» som et faktum.
//
// Data kommer fra /api/symbiose/agents, som leser et snapshot .13 speiler hit. .15 har bevisst
// ingen graf-creds, så GUI-en spør aldri Neo4j direkte.
//
// STIL: Hermes-idiomet via symbioseTheme (Morten 2026-07-23: én stil, Hermes native).

import { useEffect, useState } from "react";

import { fetchJSON } from "@/lib/api";
import { PANEL, SECTION_LABEL, toneBadge, toneText } from "@/pages/symbioseTheme";

type Skill = {
  domain: string;
  uses: number;
  passes: number;
  rate: number | null;
  quality: number | null;
  two_layer_n: number;
  two_layer_passes: number;
  grant_bearing: boolean;
};

type Agent = {
  id: string;
  kind: string;
  model: string | null;
  host: string | null;
  runtime: string | null;
  mission: string | null;
  superseded: string | null;
  last_active: string | null;
  owns_domain?: number;
  owns_operator?: number;
  skills: Skill[];
};

type Payload = {
  available: boolean;
  reason?: string;
  generated_at?: string | null;
  summary?: { registrert: number; med_maalt_kompetanse: number; uten: number };
  agents: Agent[];
};

function pct(n: number | null): string {
  return n === null || n === undefined ? "—" : `${Math.round(n * 100)}%`;
}

function SkillRow({ s }: { s: Skill }) {
  const tone = (s.rate ?? 0) >= 0.7 ? "green" : (s.rate ?? 0) < 0.4 ? "amber" : "grey";
  return (
    <div className="flex items-center justify-between gap-3 py-1 text-sm">
      <span className="truncate text-muted-foreground">{s.domain}</span>
      <span className="flex shrink-0 items-center gap-2">
        {s.grant_bearing ? (
          <span className={`border px-1.5 py-0.5 text-[10px] ${toneBadge("green")}`}>
            to-lags · {s.two_layer_passes}/{s.two_layer_n}
          </span>
        ) : (
          <span className={`border px-1.5 py-0.5 text-[10px] ${toneBadge("grey")}`}>
            ett-lags · teller ikke mot autonomi
          </span>
        )}
        <span className={`font-mono text-[0.6875rem] ${tone === "grey" ? "" : toneText(tone)}`}>
          {s.passes}/{s.uses} = {pct(s.rate)}
        </span>
      </span>
    </div>
  );
}

function AgentCard({ a }: { a: Agent }) {
  return (
    <div className={`${PANEL} p-3`}>
      <div className="flex items-baseline justify-between gap-2">
        <span className="font-medium">{a.id}</span>
        <span className="font-mono text-[10px] text-muted-foreground">{a.kind}</span>
      </div>
      {a.mission && <div className="mt-0.5 text-xs text-muted-foreground">{a.mission}</div>}
      <div className="mt-1 font-mono text-[10px] text-muted-foreground">
        {a.model ?? "—"}
        {a.host ? ` · ${a.host}` : ""}
        {a.runtime ? ` · ${a.runtime}` : ""}
      </div>
      {a.superseded && (
        <div className="mt-1 text-[11px] text-warning">supersedert: {a.superseded}</div>
      )}
      {/* eierskapet synlig også her (BL-2331) — detaljene bor i Eierskap-fanen */}
      {((a.owns_domain ?? 0) > 0 || (a.owns_operator ?? 0) > 0) && (
        <div className="mt-1 font-mono text-[10px] text-muted-foreground">
          {[
            (a.owns_domain ?? 0) > 0 ? `eier ${a.owns_domain} flater` : "",
            (a.owns_operator ?? 0) > 0 ? `drifter ${a.owns_operator}` : "",
          ]
            .filter(Boolean)
            .join(" · ")}{" "}
          → se Eierskap
        </div>
      )}
      <div className="mt-2 border-t border-border/60 pt-1">
        {a.skills.length ? (
          a.skills.map((s) => <SkillRow key={s.domain} s={s} />)
        ) : (
          <div className="py-1 text-sm text-muted-foreground">
            ingen målt kompetanse ennå — registrert, ikke opptjent
          </div>
        )}
      </div>
    </div>
  );
}

export default function SymbiosePage() {
  const [data, setData] = useState<Payload | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    fetchJSON<Payload>("/api/symbiose/agents")
      .then(setData)
      .catch((e) => setErr(String(e)));
  }, []);

  if (err) return <div className="p-6 text-sm text-warning">Kunne ikke hente flåten: {err}</div>;
  if (!data) return <div className="p-6 text-sm text-muted-foreground">Henter flåten …</div>;
  if (!data.available)
    return (
      <div className="p-6">
        <div className={`${PANEL} p-4 text-sm`}>
          <div className="font-medium text-warning">Snapshotet er ikke speilet ennå</div>
          <div className="mt-1 text-muted-foreground">{data.reason}</div>
          <div className="mt-2 text-xs text-muted-foreground">
            Dette betyr <b>ikke</b> at flåten er tom — det betyr at speilet mangler.
          </div>
        </div>
      </div>
    );

  const working = data.agents.filter((a) => a.skills.length > 0);
  const core = working.filter((a) => a.kind === "core-role");
  const fleet = working.filter((a) => a.kind !== "core-role");
  const idle = data.agents.filter((a) => a.skills.length === 0);

  return (
    <div className="flex flex-col gap-5 p-4">
      <p className="text-xs text-muted-foreground">
        {data.summary?.registrert} registrert · {data.summary?.med_maalt_kompetanse} med målt
        kompetanse · {data.summary?.uten} uten · speilet{" "}
        <span className="font-mono">{data.generated_at?.slice(0, 19) ?? "—"}</span>
      </p>

      {core.length > 0 && (
        <section>
          <div className={`${SECTION_LABEL} mb-2`}>KJERNEROLLER</div>
          <div className="grid gap-2 md:grid-cols-2">
            {core.map((a) => (
              <AgentCard key={a.id} a={a} />
            ))}
          </div>
        </section>
      )}

      {fleet.length > 0 && (
        <section>
          <div className={`${SECTION_LABEL} mb-2`}>WORKERS</div>
          <div className="grid gap-2 md:grid-cols-2">
            {fleet.map((a) => (
              <AgentCard key={a.id} a={a} />
            ))}
          </div>
        </section>
      )}

      {idle.length > 0 && (
        <section>
          <div className={`${SECTION_LABEL} mb-1`}>
            REGISTRERT UTEN MÅLT KOMPETANSE ({idle.length})
          </div>
          <p className="mb-2 text-xs text-muted-foreground">
            Disse har identitet i grafen, men ingen fasit-scoret arbeid ennå. De vises fordi en flate
            som skjulte dem ville overdrevet hvor stor den arbeidende flåten er.
          </p>
          <div className="flex flex-wrap gap-1.5">
            {idle.map((a) => (
              <span
                key={a.id}
                className="border border-border px-2 py-0.5 font-mono text-[0.6875rem] text-muted-foreground"
              >
                {a.id}
              </span>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
