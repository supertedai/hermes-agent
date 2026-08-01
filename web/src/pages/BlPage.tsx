// BlPage — BL-hovedboka i Opus-GUI-en (BL-2290, Morten 2026-07-23).
//
// Porterer :8910/bl. Hver arbeidsenhet git→:BL via bl_ledger.py, speilet til Brain BL Index.
//
// ÆRLIGHETS-REGLENE:
//   1. «reuse-suspect» er ikke pynt — det er >1 distinkt leveranse under ETT BL-nummer, altså
//      et nummer som har mistet sin betydning som arbeidsenhet. Vises som eget avsnitt.
//   2. «ikke i Brain» betyr at arbeidet finnes i git, men aldri ble fortalt. Det er en ekte
//      gjeld, ikke en formalitet — derfor eget tall i census.
//   3. Er en spørring blind, sier siden DET. Aldri «0 BL-er» som et faktum.
//
// STIL: Hermes-idiomet via symbioseTheme (Morten 2026-07-23: én stil, Hermes native).

import { useEffect, useState } from "react";

// MÅ gå via fetchJSON, ikke rå fetch: GUI-en kjører i loopback-modus, der SPA-en må ekko
// X-Hermes-Session-Token. Rå fetch sender bare cookie — som serveren ikke leser i den
// modusen — så hvert kall ble 401 og siden viste seg tom. fetchJSON håndterer BEGGE
// auth-veiene (token i loopback, cookie i gated) og base-path-en.
import { fetchJSON } from "@/lib/api";
import { PANEL, SECTION_LABEL, toneBadge, toneText } from "@/pages/symbioseTheme";

type Bl = {
  number: string;
  title: string;
  date: string;
  commits: number;
  reuse: boolean;
  brain: boolean;
};

type Suspect = { number: string; deliverables: number; title: string };

type Payload = {
  available: boolean;
  reason?: string;
  generated_at?: string | null;
  census?: { total: number | null; reuse_suspect: number | null; not_in_brain: number | null };
  recent?: Bl[];
  suspects?: Suspect[];
  recent_blind?: boolean;
  suspects_blind?: boolean;
};

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: number | null | undefined;
  tone: "grey" | "amber" | "green";
}) {
  return (
    <div className={`${PANEL} px-4 py-3`}>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div
        className={`mt-0.5 font-mono text-2xl tabular-nums ${
          tone === "grey" ? "text-foreground" : toneText(tone)
        }`}
      >
        {value === null || value === undefined ? "BLIND" : value}
      </div>
    </div>
  );
}

export default function BlPage() {
  const [data, setData] = useState<Payload | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [q, setQ] = useState("");

  useEffect(() => {
    fetchJSON<Payload>("/api/symbiose/bl")
      .then(setData)
      .catch((e) => setErr(String(e)));
  }, []);

  if (err) return <div className="p-6 text-sm text-warning">Kunne ikke hente hovedboka: {err}</div>;
  if (!data) return <div className="p-6 text-sm text-muted-foreground">Henter BL-hovedboka …</div>;
  if (!data.available)
    return (
      <div className="p-6">
        <div className={`${PANEL} p-4 text-sm`}>
          <div className="font-medium text-warning">Snapshotet er ikke speilet ennå</div>
          <div className="mt-1 text-muted-foreground">{data.reason}</div>
          <div className="mt-2 text-xs text-muted-foreground">
            Dette betyr <b>ikke</b> at hovedboka er tom.
          </div>
        </div>
      </div>
    );

  const recent = (data.recent ?? []).filter(
    (b) =>
      !q ||
      b.number.toLowerCase().includes(q.toLowerCase()) ||
      b.title.toLowerCase().includes(q.toLowerCase()),
  );

  return (
    <div className="flex flex-col gap-5 p-4">
      <p className="text-xs text-muted-foreground">
        Hver arbeidsenhet git→<code className="font-mono">:BL</code> via{" "}
        <code className="font-mono">bl_ledger.py</code>, speilet til Brain BL Index · speilet{" "}
        <span className="font-mono">{data.generated_at?.slice(0, 19) ?? "—"}</span>
      </p>

      <div className="grid gap-2 sm:grid-cols-3">
        <Stat label="BL totalt" value={data.census?.total} tone="grey" />
        <Stat
          label="reuse-suspect (>1 leveranse under ett nummer)"
          value={data.census?.reuse_suspect}
          tone={data.census?.reuse_suspect ? "amber" : "green"}
        />
        <Stat
          label="ikke fortalt i Brain"
          value={data.census?.not_in_brain}
          tone={data.census?.not_in_brain ? "amber" : "green"}
        />
      </div>

      <section>
        <div className="mb-2 flex items-center justify-between gap-3">
          <div className={SECTION_LABEL}>NYESTE BL-ER</div>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="filtrer på nummer eller tittel …"
            className="h-8 w-64 border border-border bg-background px-2 text-xs outline-none focus:border-ring"
          />
        </div>
        {data.recent_blind ? (
          <div className={`${PANEL} p-3 text-sm text-warning`}>
            Spørringen feilet — dette betyr ikke at det ikke finnes BL-er.
          </div>
        ) : (
          <div className={`${PANEL} overflow-hidden`}>
            <table className="w-full text-sm">
              <thead className="bg-muted/20 text-left text-xs text-muted-foreground">
                <tr>
                  <th className="px-3 py-2 font-medium">BL</th>
                  <th className="px-3 py-2 font-medium">dato</th>
                  <th className="px-3 py-2 text-right font-medium">commits</th>
                  <th className="px-3 py-2 font-medium">status</th>
                  <th className="px-3 py-2 font-medium">tittel</th>
                </tr>
              </thead>
              <tbody>
                {recent.map((b) => (
                  <tr key={b.number} className="border-t border-border/60 hover:bg-muted/20">
                    <td className="whitespace-nowrap px-3 py-1.5 font-mono tabular-nums">
                      {b.number}
                    </td>
                    <td className="whitespace-nowrap px-3 py-1.5 font-mono text-[0.6875rem] text-muted-foreground">
                      {b.date || "—"}
                    </td>
                    <td className="px-3 py-1.5 text-right font-mono text-[0.6875rem] text-muted-foreground">
                      {b.commits}
                    </td>
                    <td className="whitespace-nowrap px-3 py-1.5">
                      {b.reuse && (
                        <span className={`mr-1 border px-1.5 py-0.5 text-[10px] ${toneBadge("amber")}`}>
                          reuse
                        </span>
                      )}
                      <span
                        className={`text-[10px] ${b.brain ? toneText("green") : "text-muted-foreground"}`}
                      >
                        {b.brain ? "i Brain" : "ikke fortalt"}
                      </span>
                    </td>
                    <td className="px-3 py-1.5 text-muted-foreground">{b.title}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {recent.length === 0 && (
              <div className="px-3 py-4 text-sm text-muted-foreground">ingen treff på «{q}»</div>
            )}
          </div>
        )}
      </section>

      {(data.suspects?.length ?? 0) > 0 && (
        <section>
          <div className={`${SECTION_LABEL} mb-1`}>REUSE-SUSPEKTE</div>
          <p className="mb-2 text-xs text-muted-foreground">
            Mer enn én distinkt leveranse under ett nummer — nummeret har mistet sin betydning som
            arbeidsenhet.
          </p>
          <div className="grid gap-1.5 md:grid-cols-2">
            {data.suspects!.map((s) => (
              <div key={s.number} className={`${PANEL} flex items-baseline gap-2 px-3 py-1.5 text-sm`}>
                <span className="font-mono tabular-nums">{s.number}</span>
                <span className={`shrink-0 border px-1.5 py-0.5 text-[10px] ${toneBadge("amber")}`}>
                  {s.deliverables} leveranser
                </span>
                <span className="truncate text-muted-foreground">{s.title}</span>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
