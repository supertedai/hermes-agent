// KartPage — :8910/blueprint («🗺 Kart») i Opus-GUI-en (BL-2320).
//
// Det hierarkiske levende kartet: kontrollryggraden → substratet → de fem systemene
// → ærlig modenhet. STRUKTUREN ast-ekstraheres fra dashboard-KILDEN på .13 (aldri
// håndkopiert — kilden endres, kartet følger). HELSEN per flate er hentet server-side
// med samme regex som :8910 bruker; grå = ærlig ukjent.
//
// Flater som ikke er portert ennå lenker til :8910 (åpnes i ny fane) — kartet skal
// vise HELE organismen, ikke bare det GUI-en har fått egne sider for.
//
// STIL: Hermes-idiomet via symbioseTheme (Morten 2026-07-23: én stil, Hermes native).

import { useEffect, useState } from "react";

import { fetchJSON } from "@/lib/api";
import { PANEL, SECTION_LABEL, toneDot, toneText } from "@/pages/symbioseTheme";

type LoopStep = { step: string; color: string; tag: string; desc: string };
type Machine = { name: string; hw: string; desc: string; tags: string[] };
type Area = { icon: string; name: string; href: string; what: string; health: string };
type System = { num: string; title: string; desc: string; areas: Area[] };
type Mat = { name: string; color: string; what: string };

type Payload = {
  available: boolean;
  reason?: string;
  generated_at?: string | null;
  loop?: LoopStep[];
  topo?: Machine[];
  systems?: System[];
  maturity?: Mat[];
  dash_base?: string;
};

const MAT_LABEL: Record<string, string> = { green: "sunn", amber: "delvis", red: "umoden" };

// ALLE flater åpnes i GUI-en (Morten 2026-07-23: «alle tiles må rutes til native»)
// — hver :8910-rute har nå en fane i navet (native eller shell-portert), så kartet
// ruter ALDRI ut av huset. Kart-fanen er inngangsdøra; dørene skal peke innover.
const INTERNAL: Record<string, string> = {
  "/": "/symbiose?t=surveillance",
  "/agents": "/symbiose?t=aktorer",
  "/autonomy": "/symbiose?t=autonomy",
  "/bl": "/symbiose?t=bl",
  "/blueprint": "/symbiose?t=kart",
  "/channels": "/symbiose?t=channels",
  "/chat": "/symbiose?t=chat",
  "/climate": "/symbiose?t=climate",
  "/cognition": "/symbiose?t=cognition",
  "/consequences": "/symbiose?t=consequences",
  "/cyber": "/symbiose?t=cyber",
  "/defense": "/symbiose?t=defense",
  "/doi": "/symbiose?t=doi",
  "/dualego": "/symbiose?t=dualego",
  "/economy": "/symbiose?t=economy",
  "/efs": "/symbiose?t=efs",
  "/electricity": "/symbiose?t=electricity",
  "/epidemi": "/symbiose?t=epidemi",
  "/evolution": "/symbiose?t=evolution",
  "/executive": "/symbiose?t=executive",
  "/geopolitics": "/symbiose?t=geopolitics",
  "/governance": "/symbiose?t=governance",
  "/helse": "/symbiose?t=helse",
  "/immune": "/symbiose?t=immune",
  "/integrity": "/symbiose?t=integrity",
  "/learning": "/symbiose?t=learning",
  "/loop": "/symbiose?t=loop",
  "/maturity": "/symbiose?t=maturity",
  "/opus671b": "/symbiose?t=opus671b",
  "/pipeline": "/symbiose?t=pipeline",
  "/regulation": "/symbiose?t=regulation",
  "/science": "/symbiose?t=science",
  "/sources": "/symbiose?t=sources",
  "/spaceweather": "/symbiose?t=spaceweather",
  "/strategy": "/symbiose?t=strategy",
  "/vitals": "/symbiose?t=vitals",
  "/worldmodel": "/symbiose?t=worldmodel",
};

function Dot({ c }: { c: string }) {
  return <span className={`inline-block h-2 w-2 shrink-0 ${toneDot(c)}`} />;
}

export default function KartPage() {
  const [data, setData] = useState<Payload | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    fetchJSON<Payload>("/api/symbiose/kart")
      .then(setData)
      .catch((e) => setErr(String(e)));
  }, []);

  if (err) return <div className="p-6 text-sm text-warning">Kunne ikke hente kartet: {err}</div>;
  if (!data) return <div className="p-6 text-sm text-muted-foreground">Henter kartet …</div>;
  if (!data.available)
    return (
      <div className="p-6">
        <div className={`${PANEL} p-4 text-sm`}>
          <div className="font-medium text-warning">Snapshotet er ikke speilet ennå</div>
          <div className="mt-1 text-muted-foreground">{data.reason}</div>
        </div>
      </div>
    );

  return (
    <div className="flex flex-col gap-5 p-4">
      <p className="text-xs text-muted-foreground">
        Struktur fra dashboard-kilden (ast-ekstrahert, aldri håndkopiert) · helse per flate live ·
        speilet <span className="font-mono">{data.generated_at?.slice(0, 19) ?? "—"}</span>
      </p>

      <section>
        <div className={`${SECTION_LABEL} mb-2`}>KONTROLLRYGGRADEN — DEN AUTONOME SLØYFEN</div>
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {(data.loop ?? []).map((s) => (
            <div key={s.step} className={`${PANEL} p-3`}>
              <div className="flex items-center gap-2 text-sm font-medium">
                <Dot c={s.color} />
                {s.step}
                <span className={`ml-auto text-[11px] ${toneText(s.color)}`}>{s.tag}</span>
              </div>
              <div className="mt-1 text-xs text-muted-foreground">{s.desc}</div>
            </div>
          ))}
        </div>
      </section>

      <section>
        <div className={`${SECTION_LABEL} mb-2`}>SUBSTRAT — HVOR DEN KJØRER</div>
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {(data.topo ?? []).map((m) => (
            <div key={m.name} className={`${PANEL} p-3`}>
              <div className="flex items-baseline justify-between gap-2">
                <span className="text-sm font-medium">{m.name}</span>
                <span className="font-mono text-[10px] text-muted-foreground">{m.hw}</span>
              </div>
              <div className="mt-1 text-xs text-muted-foreground">{m.desc}</div>
              <div className="mt-2 flex flex-wrap gap-1">
                {m.tags.map((t) => (
                  <span
                    key={t}
                    className="border border-border bg-background/40 px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground"
                  >
                    {t}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      {(data.systems ?? []).map((sys) => (
        <section key={sys.num}>
          <div className={`${SECTION_LABEL} mb-0.5`}>
            {sys.num} · {sys.title.toUpperCase()}
          </div>
          <p className="mb-2 text-xs text-muted-foreground">{sys.desc}</p>
          <div className="grid gap-2 md:grid-cols-2 lg:grid-cols-3">
            {sys.areas.map((a) => {
              const internal = INTERNAL[a.href];
              const href = internal ?? `${data.dash_base}${a.href}`;
              return (
                <a
                  key={a.href}
                  href={href}
                  target={internal ? undefined : "_blank"}
                  rel={internal ? undefined : "noreferrer"}
                  className={`${PANEL} p-3 transition-colors hover:bg-muted/20`}
                >
                  {/* én palett (Morten): emoji-feltet fra dashbordet rendres IKKE —
                      semantikken bæres av statusprikken alene */}
                  <div className="flex items-center gap-2 text-sm font-medium">
                    <span className="truncate">{a.name}</span>
                    <span className="ml-auto flex items-center gap-1.5">
                      <Dot c={a.health} />
                      <span className="font-mono text-[10px] text-muted-foreground">
                        {internal ? "åpne" : "ekstern ↗"}
                      </span>
                    </span>
                  </div>
                  <div className="mt-1 line-clamp-2 text-xs text-muted-foreground">{a.what}</div>
                </a>
              );
            })}
          </div>
        </section>
      ))}

      <section>
        <div className={`${SECTION_LABEL} mb-1`}>ÆRLIG MODENHET</div>
        <p className="mb-2 text-xs text-muted-foreground">
          Kartet lyver ikke: rødt på dashbordet er rødt her.
        </p>
        <div className="grid gap-1.5 md:grid-cols-2">
          {(data.maturity ?? []).map((m) => (
            <div key={m.name} className={`${PANEL} flex items-center gap-2 px-3 py-1.5 text-sm`}>
              <Dot c={m.color} />
              <span className="font-medium">{m.name}</span>
              <span className="truncate text-xs text-muted-foreground">— {m.what}</span>
              <span className={`ml-auto text-[11px] ${toneText(m.color)}`}>
                {MAT_LABEL[m.color] ?? "ukjent"}
              </span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
