// ShellPage — generisk renderer for _shell-porterte :8910-faner (BL-2320).
//
// Innholdet er SANITERT HTML fra dashbordets egen renderer (server-side på .13,
// scripts/on*-attributter strippet, lenker omskrevet til absolutte :8910-URL-er).
// Én sannhetskilde: endres en spørring i dashbordet, følger denne fanen automatisk.
//
// STIL-OVERSETTELSEN skjer her, én gang, med to lag:
//   1. VAR-BROEN: dashbord-CSS-en refererer var(--green/--ink/--brd/…) — vi
//      redefinerer dem fra HERMES' tokens på containeren. All var-basert side-CSS
//      rendrer dermed i husets farger, lys som mørk, uten å røre innholdet.
//   2. KJERNEVOKABULARET (.tile/.sig/.lst/.bdg/…) restyles eksplisitt til
//      Hermes-idiomet: skarpe hjørner, border-border-paneler, mono-data.
// Ukjente bespoke-klasser arver basen og degraderer pent.
//
// SIKKERHETSBARRIEREN (Reviewer BLOCK-1): DOMPurify klient-side er den harde
// skansen foran dangerouslySetInnerHTML — graf-innholdet rendererne skriver ut
// kan bære eksternt tekstmateriale (CVE-titler, arxiv, chat), og server-regexen
// i generatoren er kun forsvar-i-dybden, aldri siste ledd.

import DOMPurify from "dompurify";
import { useEffect, useState } from "react";

import { fetchJSON } from "@/lib/api";
import { PANEL } from "@/pages/symbioseTheme";

type Payload = {
  available: boolean;
  reason?: string;
  generated_at?: string | null;
  route?: string;
  dash_base?: string;
  html?: string;
  css?: string;
};

// Lag 1+2: var-broen og kjernevokabularet. Skrevet som template-literal så alt
// bor i VÅR fil (null merge-flate mot Hermes' egne stilark).
const EMBED_CSS = `
.dash-embed{
  --bg: transparent;
  --panel: var(--color-card, rgba(127,127,127,.06));
  --brd: var(--color-border, currentColor);
  --ink: var(--color-foreground, currentColor);
  --dim: var(--color-muted-foreground, currentColor);
  --faint: var(--color-muted-foreground, currentColor);
  --green: var(--color-success, #3fb950);
  --amber: var(--color-warning, #d29922);
  --red: var(--color-destructive, #f85149);
  --blue: var(--color-primary, #58a6ff);
  --mono: ui-monospace, SFMono-Regular, Menlo, monospace;
  --sans: inherit;
  color: inherit;
  font-size: 0.8125rem;
  line-height: 1.5;
}
.dash-embed *{ border-radius: 0 !important; }
.dash-embed a{ color: var(--blue); text-decoration: none; }
.dash-embed a:hover{ text-decoration: underline; }
.dash-embed .tiles{ display:grid; gap:8px; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); margin-bottom:12px; }
.dash-embed .tile{ border:1px solid var(--brd); background: color-mix(in srgb, var(--ink) 3%, transparent); padding:10px 12px; }
.dash-embed .tile h2{ font-size:0.8125rem; font-weight:600; margin:0 0 2px; }
.dash-embed .tile .sub{ color: var(--dim); font-size:0.6875rem; margin-bottom:6px; }
.dash-embed .sig{ display:flex; justify-content:space-between; gap:12px; padding:2px 0; font-size:0.75rem; }
.dash-embed .sig .v{ font-family: var(--mono); }
.dash-embed .v.green, .dash-embed .green{ color: var(--green); }
.dash-embed .v.amber, .dash-embed .amber{ color: var(--amber); }
.dash-embed .v.red, .dash-embed .red{ color: var(--red); }
.dash-embed .v.blue, .dash-embed .blue{ color: var(--blue); }
.dash-embed .v.grey, .dash-embed .grey{ color: var(--dim); }
.dash-embed .tile.green{ border-left:2px solid var(--green); }
.dash-embed .tile.amber{ border-left:2px solid var(--amber); }
.dash-embed .tile.red{ border-left:2px solid var(--red); }
.dash-embed .tile.blue{ border-left:2px solid var(--blue); }
.dash-embed .tile.grey{ border-left:2px solid var(--brd); }
.dash-embed details.lst{ border:1px solid var(--brd); margin:8px 0; }
.dash-embed details.lst summary{ cursor:pointer; padding:6px 10px; font-size:0.75rem; color: var(--dim); user-select:none; }
.dash-embed details.lst table{ width:100%; border-collapse:collapse; font-size:0.75rem; }
.dash-embed details.lst td{ padding:3px 10px; border-top:1px solid var(--brd); vertical-align:top; }
.dash-embed td.k{ font-family: var(--mono); white-space:nowrap; }
.dash-embed td.e{ color: var(--dim); }
.dash-embed .bdg{ border:1px solid var(--brd); padding:1px 6px; font-size:0.625rem; font-family: var(--mono); }
.dash-embed .bdg.green{ border-color: color-mix(in srgb, var(--green) 50%, transparent); color: var(--green); }
.dash-embed .bdg.amber{ border-color: color-mix(in srgb, var(--amber) 50%, transparent); color: var(--amber); }
.dash-embed .bdg.red{ border-color: color-mix(in srgb, var(--red) 50%, transparent); color: var(--red); }
.dash-embed .bdg.blue{ border-color: color-mix(in srgb, var(--blue) 50%, transparent); color: var(--blue); }
.dash-embed .cp{ display:none; }
.dash-embed .gcards{ display:grid; gap:8px; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); }
.dash-embed .gcard{ border:1px solid var(--brd); padding:10px 12px; }
.dash-embed .gax{ color: var(--dim); font-size:0.6875rem; }
.dash-embed .glvl{ font-weight:600; margin:2px 0; }
.dash-embed .gkpi{ color: var(--dim); font-size:0.75rem; }
.dash-embed .essence{ color: var(--dim); font-size:0.75rem; margin-bottom:10px; }
.dash-embed .blind{ border:1px solid color-mix(in srgb, var(--amber) 40%, transparent); color: var(--amber); padding:8px 10px; font-size:0.75rem; }
`;

export default function ShellPage({ snap }: { snap: string }) {
  const [data, setData] = useState<Payload | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setData(null);
    fetchJSON<Payload>(`/api/symbiose/${snap}`)
      .then(setData)
      .catch((e) => setErr(String(e)));
  }, [snap]);

  if (err) return <div className="p-6 text-sm text-warning">Kunne ikke hente {snap}: {err}</div>;
  if (!data) return <div className="p-6 text-sm text-muted-foreground">Henter {snap} …</div>;
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
    <div className="flex flex-col gap-3 p-4">
      <p className="text-xs text-muted-foreground">
        speilet <span className="font-mono">{data.generated_at?.slice(0, 19) ?? "—"}</span> · live
        original:{" "}
        <a
          className="text-primary hover:underline"
          href={`${data.dash_base}${data.route}`}
          target="_blank"
          rel="noreferrer"
        >
          :8910{data.route}
        </a>
      </p>
      {/* sidens egen CSS først, VÅRE Hermes-overstyringer SIST — kaskaden gir
          husets stil forrang der begge treffer samme klasse */}
      {data.css ? <style>{scopeCss(data.css)}</style> : null}
      <style>{EMBED_CSS}</style>
      <div
        className="dash-embed"
        // DOMPurify = den harde barrieren; innholdet er style-fritt fra generatoren
        // (inline <style> løftes til css-feltet), så style/iframe/script forbys blankt.
        dangerouslySetInnerHTML={{
          __html: DOMPurify.sanitize(data.html ?? "", {
            FORBID_TAGS: ["style", "script", "iframe", "object", "embed", "form", "input", "link", "meta"],
            ADD_ATTR: ["target", "rel"],
          }),
        }}
      />
    </div>
  );
}

// Side-CSS-en scopes til containeren så bespoke layout (board-kolonner, vcards)
// virker uten å lekke ut i resten av GUI-en. Enkel prefiksing per regel.
function scopeCss(css: string): string {
  return css.replace(/(^|\})\s*([^{}@]+)\{/g, (_m, brace: string, sel: string) => {
    const scoped = sel
      .split(",")
      .map((s: string) => `.dash-embed ${s.trim()}`)
      .join(", ");
    return `${brace} ${scoped}{`;
  });
}
