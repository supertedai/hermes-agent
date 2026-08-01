// SectionsPage — generisk native renderer for bespoke-faner (BL-2336 bølge 3).
//
// Seksjons-kontrakten er skalerings-grepet for de 24 bespoke fanene: hver fane
// får en strukturert GENERATOR (samme spørringer som rendereren, import td),
// som emitter en seksjons-liste — og DENNE ene siden rendrer alle. Ny bespoke
// fane = generator-funksjon, null ny React.
//
// Kontrakt: {kind: "stats"|"pills"|"series"|"table"|"kv", ...} — se typene.
// Ærlighet overalt: blind ≠ tom, trunkering aldri stille, toner fra data.

import { useEffect, useState } from "react";

import { fetchJSON } from "@/lib/api";
import { PANEL, SECTION_LABEL, toneBadge, toneText } from "@/pages/symbioseTheme";

type Stat = { label: string; value: string; tone?: string };
type Pill = { label: string; value: unknown; tone?: string; blind?: boolean };
type Serie = { name: string; data: number[] };
type Section =
  | { kind: "stats"; title?: string; items: Stat[] }
  | { kind: "pills"; title?: string; items: Pill[] }
  | { kind: "series"; title?: string; series: Serie[] }
  | { kind: "table"; title: string; cols: string[]; rows: unknown[][]; total?: number; blind?: boolean; row_tones?: string[] }
  | { kind: "kv"; title?: string; pairs: [string, string][] };
type Tab = { blind?: boolean; grunn?: string; note?: string; sections?: Section[] };
type Payload = { available: boolean; reason?: string; generated_at?: string | null; tabs?: Record<string, Tab> };

function Sparkline({ data }: { data: number[] }) {
  if (data.length < 2) return null;
  const w = 220;
  const h = 34;
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

function Render({ s }: { s: Section }) {
  if (s.kind === "stats")
    return (
      <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-4">
        {s.items.map((it) => (
          <div key={it.label} className={`${PANEL} px-4 py-3`}>
            <div className="text-xs text-muted-foreground">{it.label}</div>
            <div className={`mt-0.5 font-mono text-xl tabular-nums ${it.tone ? toneText(it.tone) : "text-foreground"}`}>
              {it.value}
            </div>
          </div>
        ))}
      </div>
    );
  if (s.kind === "pills")
    return (
      <div className="flex flex-wrap gap-1.5">
        {s.items.map((p) => (
          <span key={p.label} className={`border px-2 py-1 text-xs ${p.blind ? toneBadge("grey") : toneBadge(p.tone ?? "grey")}`}>
            {p.label}: <span className="font-mono">{p.blind ? "BLIND" : String(p.value ?? "—")}</span>
          </span>
        ))}
      </div>
    );
  if (s.kind === "series")
    return (
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {s.series.map((sr) => (
          <div key={sr.name} className={`${PANEL} p-3`}>
            <div className="mb-1 font-mono text-xs text-muted-foreground">{sr.name}</div>
            <Sparkline data={sr.data} />
          </div>
        ))}
      </div>
    );
  if (s.kind === "kv")
    return (
      <div className={`${PANEL} p-3`}>
        {s.pairs.map(([k, v]) => (
          <div key={k} className="flex justify-between gap-4 py-0.5 text-sm">
            <span className="text-muted-foreground">{k}</span>
            <span className="font-mono text-xs">{v}</span>
          </div>
        ))}
      </div>
    );
  // table
  if (s.blind)
    return (
      <div className={`${PANEL} p-3 text-sm text-warning`}>
        {s.title}: spørringen feilet (BLIND) — betyr ikke «ingen rader».
      </div>
    );
  if (!s.rows.length)
    return <div className={`${PANEL} p-3 text-sm text-muted-foreground`}>{s.title}: ingen rader ✓</div>;
  return (
    <div className={`${PANEL} overflow-x-auto`}>
      <table className="w-full text-sm">
        <thead className="bg-muted/20 text-left text-xs text-muted-foreground">
          <tr>{s.cols.map((c) => <th key={c} className="px-3 py-2 font-medium">{c}</th>)}</tr>
        </thead>
        <tbody>
          {s.rows.map((r, i) => (
            <tr key={i} className="border-t border-border/60 hover:bg-muted/20">
              {r.map((c, j) => (
                <td key={j} className={`max-w-[26rem] truncate px-3 py-1.5 font-mono text-[0.6875rem] ${j === 0 && s.row_tones?.[i] ? toneText(s.row_tones[i]) : "text-muted-foreground"}`}>
                  {String(c ?? "—")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {(s.total ?? s.rows.length) > s.rows.length && (
        <div className="border-t border-border/60 px-3 py-1.5 text-xs text-muted-foreground">
          viser {s.rows.length} av {s.total}
        </div>
      )}
    </div>
  );
}

export default function SectionsPage({ snap, src = "bespoke" }: { snap: string; src?: string }) {
  const [data, setData] = useState<Payload | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setData(null);
    fetchJSON<Payload>(`/api/symbiose/${src}`)
      .then(setData)
      .catch((e) => setErr(String(e)));
  }, [snap, src]);

  if (err) return <div className="p-6 text-sm text-warning">Kunne ikke hente {snap}: {err}</div>;
  if (!data) return <div className="p-6 text-sm text-muted-foreground">Henter {snap} …</div>;
  const t = data.tabs?.[snap];
  if (!data.available || !t)
    return (
      <div className="p-6">
        <div className={`${PANEL} p-4 text-sm`}>
          <div className="font-medium text-warning">Snapshotet er ikke speilet ennå</div>
          <div className="mt-1 text-muted-foreground">{data.reason ?? `fane '${snap}' mangler`}</div>
        </div>
      </div>
    );
  if (t.blind)
    return (
      <div className="p-6">
        <div className={`${PANEL} p-4 text-sm text-warning`}>BLIND: {t.grunn} — betyr ikke at flaten er tom.</div>
      </div>
    );

  return (
    <div className="flex flex-col gap-5 p-4">
      <p className="text-xs text-muted-foreground">
        {t.note ? `${t.note} · ` : ""}speilet{" "}
        <span className="font-mono">{data.generated_at?.slice(0, 19) ?? "—"}</span>
      </p>
      {(t.sections ?? []).map((s, i) => (
        <section key={i}>
          {"title" in s && s.title && <div className={`${SECTION_LABEL} mb-2`}>{s.title.toUpperCase()}</div>}
          <Render s={s} />
        </section>
      ))}
    </div>
  );
}
