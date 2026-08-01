// TilesPage — NATIVE tile-fane (BL-2336 bølge 2: Surveillance/Chat/Consequences).
//
// Strukturert JSON fra opus_tiles_snapshot (dashbordets tile-kontrakt parset
// server-side) → ren Hermes-React. Ingen HTML-innbygging. Lister er native
// <details> med badge-toner; trunkering aldri stille («viser 60 av N»).

import { useEffect, useState } from "react";

import { fetchJSON } from "@/lib/api";
import { PANEL, SECTION_LABEL, toneBadge, toneDot, toneText } from "@/pages/symbioseTheme";

type Sig = { label: string; value: string; tone: string };
type Tile = { title: string; tone: string; sub: string; signals: Sig[] };
type Row = { tone: string; badge: string; cells: string[] };
type Lst = { title: string; blind: boolean; rows: Row[]; total?: number };
type Tab = { blind: boolean; grunn?: string; tiles?: Tile[]; lists?: Lst[] };
type Payload = {
  available: boolean;
  reason?: string;
  generated_at?: string | null;
  tabs?: Record<string, Tab>;
};

export default function TilesPage({ snap }: { snap: string }) {
  const [data, setData] = useState<Payload | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setData(null);
    fetchJSON<Payload>("/api/symbiose/tiles")
      .then(setData)
      .catch((e) => setErr(String(e)));
  }, [snap]);

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
        <div className={`${PANEL} p-4 text-sm text-warning`}>
          BLIND: {t.grunn} — betyr ikke at flaten er tom.
        </div>
      </div>
    );

  return (
    <div className="flex flex-col gap-4 p-4">
      <p className="text-xs text-muted-foreground">
        speilet{" "}
        <span className="font-mono">{data.generated_at?.slice(0, 19) ?? "—"}</span>
      </p>

      <div className="grid gap-2 md:grid-cols-2 lg:grid-cols-3">
        {(t.tiles ?? []).map((tile, i) => (
          <div key={i} className={`${PANEL} p-3`}>
            <div className="flex items-center gap-2 text-sm font-medium">
              <span className={`inline-block h-2 w-2 shrink-0 ${toneDot(tile.tone)}`} />
              <span className="truncate">{tile.title}</span>
            </div>
            {tile.sub && <div className="mt-0.5 text-xs text-muted-foreground">{tile.sub}</div>}
            <div className="mt-2 space-y-0.5">
              {tile.signals.map((s, j) => (
                <div key={j} className="flex items-baseline justify-between gap-3 text-xs">
                  <span className="truncate text-muted-foreground">{s.label}</span>
                  <span className={`shrink-0 font-mono ${toneText(s.tone)}`}>{s.value}</span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      {(t.lists ?? []).map((l, i) => (
        <section key={i}>
          <details className={`${PANEL}`} open={l.rows.length > 0}>
            <summary className="cursor-pointer px-3 py-2 text-xs text-muted-foreground select-none">
              <span className={SECTION_LABEL}>{l.title.toUpperCase()}</span>
            </summary>
            {l.blind ? (
              <div className="border-t border-border/60 px-3 py-2 text-sm text-warning">
                spørringen feilet (BLIND) — betyr ikke «ingen rader».
              </div>
            ) : l.rows.length === 0 ? (
              <div className="border-t border-border/60 px-3 py-2 text-sm text-muted-foreground">
                ingen rader ✓
              </div>
            ) : (
              <div className="overflow-x-auto border-t border-border/60">
                <table className="w-full text-sm">
                  <tbody>
                    {l.rows.map((r, j) => (
                      <tr key={j} className="border-t border-border/40 first:border-t-0 hover:bg-muted/20">
                        <td className="whitespace-nowrap px-3 py-1.5">
                          <span className={`border px-1.5 py-0.5 text-[10px] ${toneBadge(r.tone)}`}>
                            {r.badge || "·"}
                          </span>
                        </td>
                        {r.cells.map((c, k) => (
                          <td key={k} className="max-w-[24rem] truncate px-3 py-1.5 font-mono text-[0.6875rem] text-muted-foreground">
                            {c || "—"}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
                {(l.total ?? l.rows.length) > l.rows.length && (
                  <div className="border-t border-border/60 px-3 py-1.5 text-xs text-muted-foreground">
                    viser {l.rows.length} av {l.total}
                  </div>
                )}
              </div>
            )}
          </details>
        </section>
      ))}
    </div>
  );
}
