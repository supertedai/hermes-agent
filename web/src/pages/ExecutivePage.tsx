// ExecutivePage — :8910/executive i Opus-GUI-en (BL-2320).
//
// Mortens 5 spørsmål besvart på ett skjermbilde, + de tre ASI-søylene. Data fra
// /api/symbiose/executive — snapshotet .13 speiler (samme helpers som :8910 bruker,
// BL-942-komposisjonen). ÆRLIGHET: BLIND/grå vises som nettopp det; mission-status
// er VERSTE svar, aldri et gjennomsnitt som pynter.
//
// STIL: Hermes-idiomet via symbioseTheme — ikke :8910s fargede kanter (Morten
// 2026-07-23: én stil, Hermes native).

import { useEffect, useState } from "react";

import { fetchJSON } from "@/lib/api";
import { PANEL, SECTION_LABEL, toneBadge, toneDot, toneText } from "@/pages/symbioseTheme";

type Answer = {
  q: string;
  label: string;
  color: string;
  weakest?: string[];
  // td._arrow gir [symbol, farge, delta] — vi bruker de to første, delta ignoreres bevisst.
  arrows?: Record<string, [string, string, ...unknown[]]>;
  tiles?: { name: string; color: string }[];
  weakest_family?: { name: string; closed_pct: number } | null;
  critical_blindspots?: number | null;
  axis?: string | null;
  note?: string | null;
  blockers?: string[];
  blind?: string[];
  dirty_files?: number | null;
  error?: string;
};

type Pillar = { name: string; color: string; headline: string; detail: string };

type Payload = {
  available: boolean;
  reason?: string;
  generated_at?: string | null;
  mission?: { color: string; label: string };
  answers?: Answer[];
  pillars?: Pillar[];
};

function AnswerCard({ a }: { a: Answer }) {
  return (
    <div className={`${PANEL} p-3`}>
      <div className="flex items-center gap-2">
        <span className={`inline-block h-2 w-2 shrink-0 ${toneDot(a.color)}`} />
        <span className="text-xs text-muted-foreground">{a.q}</span>
      </div>
      <div className={`mt-1 text-sm font-medium ${toneText(a.color)}`}>{a.label}</div>
      <div className="mt-2 space-y-1 text-xs text-muted-foreground">
        {a.error && <div>feil: {a.error} — svaret er blindt, ikke «grønt»</div>}
        {a.arrows && (
          <div className="font-mono text-[0.6875rem]">
            {Object.entries(a.arrows).map(([k, [chr, col]]) => (
              <span key={k} className={`mr-3 ${toneText(col)}`}>
                {k} {chr}
              </span>
            ))}
          </div>
        )}
        {(a.weakest?.length ?? 0) > 0 && <div>svakest akser: {a.weakest!.join(", ")}</div>}
        {a.tiles && (
          <div className="flex flex-wrap gap-1.5">
            {a.tiles.map((t) => (
              <span key={t.name} className={`border px-1.5 py-0.5 text-[10px] ${toneBadge(t.color)}`}>
                {t.name}
              </span>
            ))}
          </div>
        )}
        {a.weakest_family && (
          <div>
            svakest familie: {a.weakest_family.name} ({a.weakest_family.closed_pct}% lukket)
          </div>
        )}
        {(a.critical_blindspots ?? 0) > 0 && <div>{a.critical_blindspots} kritiske blindsoner åpne</div>}
        {a.axis && <div>akse: {a.axis}</div>}
        {a.note && <div>{a.note}</div>}
        {(a.blockers?.length ?? 0) > 0 && (
          <ul className="list-inside list-disc">
            {a.blockers!.map((b) => (
              <li key={b}>{b}</li>
            ))}
          </ul>
        )}
        {a.dirty_files != null && <div>{a.dirty_files} filer uncommitted (fundament-flux)</div>}
      </div>
    </div>
  );
}

export default function ExecutivePage() {
  const [data, setData] = useState<Payload | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    fetchJSON<Payload>("/api/symbiose/executive")
      .then(setData)
      .catch((e) => setErr(String(e)));
  }, []);

  if (err) return <div className="p-6 text-sm text-warning">Kunne ikke hente Executive: {err}</div>;
  if (!data) return <div className="p-6 text-sm text-muted-foreground">Henter Executive …</div>;
  if (!data.available)
    return (
      <div className="p-6">
        <div className={`${PANEL} p-4 text-sm`}>
          <div className="font-medium text-warning">Snapshotet er ikke speilet ennå</div>
          <div className="mt-1 text-muted-foreground">{data.reason}</div>
        </div>
      </div>
    );

  const m = data.mission;
  return (
    <div className="flex flex-col gap-4 p-4">
      <div className={`${PANEL} p-3`}>
        <div className={SECTION_LABEL}>MISSION STATUS</div>
        <div className="mt-1 flex items-center gap-2">
          <span className={`inline-block h-2 w-2 ${toneDot(m?.color)}`} />
          <span className={`text-sm font-medium ${toneText(m?.color)}`}>{m?.label ?? "BLIND"}</span>
          <span className="ml-auto font-mono text-[0.6875rem] text-muted-foreground">
            speilet {data.generated_at?.slice(0, 19) ?? "—"}
          </span>
        </div>
        <p className="mt-1 text-xs text-muted-foreground">
          De 5 spørsmålene syntetisert fra live-helpers (BL-942) — verste svar setter status.
        </p>
      </div>

      <div className="grid gap-2 md:grid-cols-2">
        {(data.answers ?? []).map((a) => (
          <AnswerCard key={a.q} a={a} />
        ))}
      </div>

      {(data.pillars?.length ?? 0) > 0 && (
        <section>
          <div className={`${SECTION_LABEL} mb-2`}>DE TRE ASI-SØYLENE</div>
          <div className="grid gap-2 sm:grid-cols-3">
            {data.pillars!.map((p) => (
              <div key={p.name} className={`${PANEL} p-3`}>
                <div className="flex items-center gap-2 text-sm font-medium">
                  <span className={`inline-block h-2 w-2 ${toneDot(p.color)}`} />
                  {p.name}
                </div>
                <div className={`mt-0.5 text-xs ${toneText(p.color)}`}>{p.headline}</div>
                <div className="mt-1 text-xs text-muted-foreground">{p.detail}</div>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
