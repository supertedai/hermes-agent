// SymbioseHub — ÉN inngang i Opus-GUI-en, gruppert side-navigasjon inni. BL-2290/2320/2327.
//
// HVORFOR SIDE-NAV, IKKE TOPP-STRIPE: med hele :8910 portert (38 flater) er en
// horisontal stripe ubrukelig. Mønsteret er SkillsPage' kategorikolonne — Hermes'
// eget idiom for akkurat dette. Gruppene ER Kart-systemene (01–05), så mental
// modell i kartet og navigasjonen er samme modell.
//
// MERGE-FLATEN står som før: ETT punkt i Hermes' App.tsx uansett antall faner.
// Ny fane = én linje i GROUPS her + (for _shell-faner) én i opus_shell_snapshot.TABS.
//
// BL-2369: 05-gruppen er GRAF-DREVET. Jetstream-loopen (BL-2356/2358) promoterer
// kilder i NYE domener autonomt — en statisk fane-liste gjorde dem usynlige.
// Huben leser :IngestSourceSpec-registeret (hentet via unified-APIets read-only
// GET av opus_domain_snapshot på .13 og speilet i domains.json — samme kreditiv-
// grense som alt annet: .15 ser aldri grafen) og render dynamiske faner for
// domener den statiske lista ikke bærer. DomainPage har register-fallbacken.
//
// BL-2375: HELE 05-gruppen rendres fra grafen. opus_ownership stempler
// :Surface{nav_group:'05'} med label/renderer/hint/rekkefølge + navngitt eier
// (OWNS) — generatoren emitter nav05 i domains.json, og gruppa under tegnes
// derfra med eier synlig per fane. Den statiske 05-lista i GROUPS er kun
// BLIND-FALLBACK (nav05 uleselig → gammel oppførsel, aldri en tom gruppe).

import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import {
  Activity,
  Gauge,
  Box,
  Brain,
  CloudSun,
  Cpu,
  Database,
  FileText,
  FlaskConical,
  Gavel,
  GitMerge,
  Globe,
  Globe2,
  GraduationCap,
  Hash,
  HeartPulse,
  Hexagon,
  Infinity as InfinityIcon,
  LineChart,
  Lock,
  Map,
  MessageSquare,
  MessagesSquare,
  Microscope,
  Network,
  Plug,
  Satellite,
  Scale,
  Settings,
  Shield,
  ShieldCheck,
  Star,
  Stethoscope,
  Target,
  TrendingUp,
  Users,
  Waves,
  Zap,
} from "lucide-react";

import { fetchJSON } from "@/lib/api";
import BlPage from "@/pages/BlPage";
import DomainPage from "@/pages/DomainPage";
import TilesPage from "@/pages/TilesPage";
import SectionsPage from "@/pages/SectionsPage";
import EierskapPage from "@/pages/EierskapPage";
import ExecutivePage from "@/pages/ExecutivePage";
import KartPage from "@/pages/KartPage";
import SymbiosePage from "@/pages/SymbiosePage";

type Tab = {
  id: string;
  label: string;
  icon: typeof Network;
  hint: string;
  render: () => ReactNode;
};

type Group = { title: string; tabs: Tab[] };

// Gruppene speiler Kart-systemene 01–05 — samme struktur som organismen selv.
const GROUPS: Group[] = [
  {
    title: "OVERSIKT",
    tabs: [
      { id: "kart", label: "Kart", icon: Map, hint: "hele organismen — kontrollryggrad, substrat, de fem systemene, ærlig modenhet", render: () => <KartPage /> },
      { id: "executive", label: "Executive", icon: Star, hint: "de 5 spørsmålene på ett skjermbilde — verste svar setter mission status", render: () => <ExecutivePage /> },
      { id: "surveillance", label: "Surveillance", icon: Hexagon, hint: "fail-closed meta-laget: HAZOP · Coordinator · Oracle · Autohealer · Pipeline", render: () => <TilesPage snap="surveillance" /> },
      { id: "ressurser", label: "Ressurser", icon: Gauge, hint: "maskinparken målt — verter, endepunkter, oppdaget HW, flaskehalser, HW-forslag", render: () => <SectionsPage snap="ressurser" src="ressurser" /> },
      { id: "orkestrering", label: "Orkestrering", icon: GitMerge, hint: "kø · dispatcher · daemon-kadens · ledig kapasitet vs arbeid — hvor arbeid står og venter", render: () => <SectionsPage snap="orkestrering" src="orkestrering" /> },
      { id: "kompetanse", label: "Kompetanse", icon: GraduationCap, hint: "utfall→sansing: kompetanse-hull (to-lags-nederlag) og beviste styrker — den døde korpus→smie-buen, nå synlig og handlbar (BL-2483)", render: () => <SectionsPage snap="kompetanse" src="kompetanse" /> },
      { id: "eierskap", label: "Eierskap", icon: Users, hint: "hver fane, tile og tjeneste har en navngitt eier — dekningen skal opp, ueid-lista ned", render: () => <EierskapPage /> },
      { id: "duty_resolver", label: "Duty-triage", icon: HeartPulse, hint: "autonom triage av duty needs_human-køen: arkiver fjernede, lukk friske, restart ekte-syke — Morten aldri flaskehals (BL-2490)", render: () => <SectionsPage snap="duty_resolver" src="duty_resolver" /> },
      { id: "fleet_worker", label: "Fleet Worker", icon: Box, hint: "gym-workerens modell + MoA — Symbiose-eid, Morten-styrt (IKKE hardcode); beslutning A = lokal modell + MoA av (ekstern MoA henger i den nøkkel-frie sandkassen)", render: () => <SectionsPage snap="fleet_worker" src="fleet_worker" /> },
    ],
  },
  {
    title: "01 · STYRING & SELV",
    tabs: [
      { id: "autonomy", label: "Autonomi", icon: Settings, hint: "mål→plan→handling→dom→RSI-trapp→konstitusjon", render: () => <SectionsPage snap="autonomy" /> },
      { id: "loop", label: "ASI Loop", icon: InfinityIcon, hint: "er den kognitive+vitenskapelige sløyfen lukket ende-til-ende?", render: () => <SectionsPage snap="loop" /> },
      { id: "opus671b", label: "Opus (GLM-5.2)", icon: Cpu, hint: "resonnerings-cortexen — live tankestrøm", render: () => <SectionsPage snap="opus671b" /> },
      { id: "dualego", label: "Homo Fluxus", icon: Waves, hint: "EFC vendt innover: Morten ↔ Opus som to flyt-selv", render: () => <SectionsPage snap="dualego" /> },
    ],
  },
  {
    title: "02 · KOGNISJON & LÆRING",
    tabs: [
      { id: "cognition", label: "Cognition", icon: Brain, hint: "kognisjon · minne · læring · prediksjon · epistemikk · selvforbedring", render: () => <SectionsPage snap="cognition" /> },
      { id: "laering", label: "Lærings-stinget", icon: TrendingUp, hint: "lærings-stinget: verdensmodell-erfaringer, prediksjon→validering, innsikter, kompetanse — den ekte læringen, ærlig (/learning/status='0' er narrow-kanal, BL-2486)", render: () => <SectionsPage snap="laering" src="laering" /> },
      { id: "vitals", label: "Vitals", icon: Activity, hint: "hukommelses-tiers, ego/selv, introspeksjon, selv-koherens", render: () => <SectionsPage snap="vitals" /> },
      { id: "worldmodel", label: "Worldmodell", icon: Globe, hint: "den ENE lærings-huben — alt lærer inn, alt trekker erfaring ut", render: () => <SectionsPage snap="worldmodel" /> },
      { id: "consequences", label: "Consequences", icon: Zap, hint: "måler→konsekvens-bussen: endrer målingene faktisk det vi gjør?", render: () => <TilesPage snap="consequences" /> },
      { id: "immune", label: "Immunforsvar", icon: ShieldCheck, hint: "wire-integritet: hver loop lukket produsent↔forbruker", render: () => <SectionsPage snap="immune" /> },
      { id: "evolution", label: "Evolusjon", icon: TrendingUp, hint: "daglige tidsserier — ECE, autonomi, læringstakt, konvergens", render: () => <SectionsPage snap="evolution" /> },
      { id: "agenter", label: "Agenter (CV)", icon: Network, hint: "flåten med målt kompetanse — hvem bærer autonomi", render: () => <SymbiosePage /> },
      { id: "aktorer", label: "Agent-aktivitet", icon: Users, hint: "per aktør — utført, verdicts, mål, effektivitet", render: () => <SectionsPage snap="aktorer" /> },
    ],
  },
  {
    title: "03 · SANNHET & INTEGRITET",
    tabs: [
      { id: "integrity", label: "Source-of-Truth", icon: Lock, hint: "er grafen ankret · verifisert · ikke-driftende per :AuthorityContract", render: () => <SectionsPage snap="integrity" /> },
      { id: "governance", label: "Governance", icon: Scale, hint: "per signal: styrer den, eller vises den bare?", render: () => <SectionsPage snap="governance" /> },
      { id: "efs", label: "EFS", icon: Box, hint: "epistemisk konservering: self-sealing credence, EFC↔ΛCDM-symmetri", render: () => <SectionsPage snap="efs" /> },
      { id: "pipeline", label: "Ingest Pipeline", icon: GitMerge, hint: "ingest→govern→motorer→verdict — ett organisme", render: () => <SectionsPage snap="pipeline" /> },
      { id: "maturity", label: "Modenhet", icon: FlaskConical, hint: "ærlig modenhet per evne: SCM, ontologi, minne, multi-tenant", render: () => <SectionsPage snap="maturity" /> },
    ],
  },
  {
    title: "04 · DRIFT & OVERVÅKNING",
    tabs: [
      { id: "strategy", label: "Strategy", icon: Target, hint: "hele backloggen ranket etter ROI mot AGI/ASI", render: () => <SectionsPage snap="strategy" /> },
      { id: "bl", label: "BL", icon: Hash, hint: "hovedboka — hver arbeidsenhet git→:BL", render: () => <BlPage /> },
    ],
  },
  {
    title: "05 · VERDEN & DOMENER",
    tabs: [
      { id: "economy", label: "Economy", icon: LineChart, hint: "markeder & makro → verdensmodellen", render: () => <SectionsPage snap="economy" /> },
      { id: "geopolitics", label: "Geopolitikk", icon: Globe2, hint: "GDELT-tensjon, spenningspar, P(eskalering)", render: () => <SectionsPage snap="geopolitics" /> },
      { id: "cyber", label: "Cyber", icon: Shield, hint: "NVD CVE-strøm, kritikalitet, selskaps-koblinger", render: () => <DomainPage domain="cyber" /> },
      { id: "regulation", label: "Regulering", icon: Gavel, hint: "US+UK+EU-regulering, sektor-prior, selskaps-treff", render: () => <DomainPage domain="regulation" /> },
      { id: "climate", label: "Klima", icon: CloudSun, hint: "global temp-anomali + CO2", render: () => <DomainPage domain="climate" /> },
      { id: "epidemi", label: "Epidemi", icon: Stethoscope, hint: "global epidemiologi, koblet til land", render: () => <DomainPage domain="health" /> },
      { id: "science", label: "Vitenskap", icon: Microscope, hint: "innovasjons-tempo — arXiv per nøkkelfelt", render: () => <DomainPage domain="science" /> },
      { id: "spaceweather", label: "Rom", icon: Satellite, hint: "romvær — Kp-indeks, storm→infrastruktur-risiko", render: () => <DomainPage domain="spaceweather" /> },
      { id: "electricity", label: "Kraft", icon: Plug, hint: "europeisk strøm — day-ahead pris + fornybar-andel", render: () => <DomainPage domain="electricity" /> },
      { id: "defense", label: "Forsvar", icon: ShieldCheck, hint: "allianser + militærutgifter + allianse-mediert tensjon", render: () => <SectionsPage snap="defense" /> },
      { id: "learning", label: "Læring", icon: GraduationCap, hint: "attribusjon, Brier/reliabilitet, kilde-pålitelighet", render: () => <SectionsPage snap="learning" /> },
      { id: "sources", label: "Kilder", icon: Database, hint: "hver kilde som modellert entitet: dekning/ferskhet/treffsikkerhet", render: () => <SectionsPage snap="sources" /> },
      { id: "helse", label: "Health", icon: HeartPulse, hint: "A7 eier-klinisk cockpit — Morten-autorisert; kun GUI-hjemmet", render: () => <SectionsPage snap="helse" src="helse-native" /> },
      { id: "chat", label: "Chat", icon: MessageSquare, hint: "produksjons-chatten som kontroll-loop", render: () => <TilesPage snap="chat" /> },
      { id: "channels", label: "Channels", icon: MessagesSquare, hint: "forsknings-kanaler og team-flater", render: () => <SectionsPage snap="channels" /> },
      { id: "doi", label: "DOI", icon: FileText, hint: "DOI-verdig innsikt — propose-first, ORCID-kryssvalidert", render: () => <SectionsPage snap="doi" /> },
    ],
  },
];

const ALL_TABS: Tab[] = GROUPS.flatMap((g) => g.tabs);

// ── Graf-drevne 05-faner (BL-2369) ─────────────────────────────────────────
// Register-domener som ALLEREDE bæres av en statisk fane over: energy = Kraft
// (entsoe/eia; snapshot-nøkkelen heter electricity), health = Epidemi. Et
// register-domene utenfor denne mengden får en dynamisk fane automatisk.
const COVERED_DOMAINS = new Set([
  "economy", "geopolitics", "cyber", "regulation", "climate", "health",
  "science", "spaceweather", "energy", "electricity", "defense",
]);

// Prefiks fordi register-domener kan kollidere med statiske fane-id-er i andre
// grupper ("cognition" er alt en 02-fane for Symbiosens EGEN kognisjon).
const DYN_PREFIX = "dom-";

type RegisterBlock = { blind?: boolean; domains?: Record<string, unknown[]> };
type NavTab = {
  id: string;
  label?: string | null;
  kind?: string | null;
  ref?: string | null;
  hint?: string | null;
  src?: string | null;
  owner?: string | null;
};
type DomainsPayload = {
  available?: boolean;
  domains?: Record<string, unknown>;
  register?: RegisterBlock;
  nav05?: { blind?: boolean; tabs?: NavTab[] };
};

function dynTab(domain: string): Tab {
  return {
    id: DYN_PREFIX + domain,
    label: domain.charAt(0).toUpperCase() + domain.slice(1),
    icon: Database,
    hint: `graf-drevet domenefane — ${domain}: generisk KPI/signal-flate (:Observation/:Trend/:Anomaly) + kilderegister fra :IngestSourceSpec`,
    render: () => <DomainPage domain={domain} />,
  };
}

// BL-2375: ikoner er PRESENTASJON og bor i koden — alt annet ved 05-fanene
// (eksistens, label, renderer, hint, rekkefølge, eier) kommer fra grafen.
const ICON_05: Record<string, typeof Network> = {
  economy: LineChart, geopolitics: Globe2, cyber: Shield, regulation: Gavel,
  climate: CloudSun, epidemi: Stethoscope, science: Microscope,
  spaceweather: Satellite, electricity: Plug, defense: ShieldCheck,
  learning: GraduationCap, sources: Database, helse: HeartPulse,
  chat: MessageSquare, channels: MessagesSquare, doi: FileText,
};

// Graf-navoppføring → fane. Ukjent renderer-kind tegnes som ÆRLIG feil-flate —
// aldri stille utelatt (en :Surface med skrivefeil skal synes, ikke forsvinne).
function navTab(n: NavTab): Tab {
  const ref = n.ref ?? n.id;
  const render =
    n.kind === "domain" ? () => <DomainPage domain={ref} />
    : n.kind === "tiles" ? () => <TilesPage snap={ref} />
    : n.kind === "section" ? () => <SectionsPage snap={ref} src={n.src ?? "bespoke"} />
    : () => (
        <div className="p-6 text-sm text-warning">
          ukjent renderer-kind «{String(n.kind)}» for '{n.id}' fra grafen — flaten kan ikke tegnes.
        </div>
      );
  return {
    id: n.id,
    label: n.label || n.id,
    icon: ICON_05[n.id] ?? Database,
    hint: `${n.hint ?? "graf-drevet fane"} · eier: ${n.owner ?? "UEID"}`,
    render,
  };
}

// Fanen ligger i URL-en (?t=bl) så en fane kan deles og bokmerkes. Validering
// mot fane-lista skjer i render (BL-2369): dynamiske faner finnes først når
// registeret har svart, så en for-tidlig ukjent-sjekk ville kastet deep-links.
function readTab(): string {
  if (typeof window === "undefined") return ALL_TABS[0].id;
  return new URLSearchParams(window.location.search).get("t") ?? ALL_TABS[0].id;
}

export default function SymbioseHub() {
  const [active, setActive] = useState<string>(readTab);
  // null = domains.json ikke hentet ennå; "feilet" = hentingen feilet (statisk
  // fallback — nav-en dikter aldri faner den ikke kan belegge).
  const [payload, setPayload] = useState<DomainsPayload | "feilet" | null>(null);

  useEffect(() => {
    const onPop = () => setActive(readTab());
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  useEffect(() => {
    fetchJSON<DomainsPayload>("/api/symbiose/domains")
      .then(setPayload)
      .catch(() => setPayload("feilet"));
  }, []);

  function select(id: string) {
    setActive(id);
    const url = new URL(window.location.href);
    url.searchParams.set("t", id);
    window.history.pushState({}, "", url);
  }

  // BL-2375: 05-gruppa tegnes fra GRAFEN. Fallback-kjede, ærlig i hvert ledd:
  //   nav05 frisk        → grafen er sannheten (eksistens/label/renderer/eier)
  //   nav05 blind/borte  → statisk liste + BL-2369-register-avledning (union av
  //                        register- og snapshot-domener utenfor statisk dekning)
  //   payload ikke lastet → statisk liste (kuraterte deep-links virker straks)
  const p = payload === "feilet" ? null : payload;
  const nav = p?.nav05;
  const navTabs = !nav?.blind && nav?.tabs?.length ? nav.tabs.map(navTab) : null;
  const dynDomains =
    p && !navTabs
      ? [
          ...new Set([
            ...Object.keys(p.register?.domains ?? {}),
            ...Object.keys(p.domains ?? {}),
          ]),
        ]
          .filter((d) => !COVERED_DOMAINS.has(d))
          .sort()
      : null;

  const groups = GROUPS.map((g) =>
    g.title === "05 · VERDEN & DOMENER"
      ? {
          ...g,
          tabs: navTabs ?? (dynDomains?.length ? [...g.tabs, ...dynDomains.map(dynTab)] : g.tabs),
        }
      : g,
  );
  const allTabs = groups.flatMap((g) => g.tabs);
  const tab = allTabs.find((t) => t.id === active) ?? allTabs[0];
  // deep-link til en dynamisk fane før payloaden har svart: vis vente-tilstand
  // i innholdsflaten i stedet for å blinke innom første fane.
  const pendingDyn = active.startsWith(DYN_PREFIX) && payload === null && tab.id !== active;

  return (
    <div className="flex h-full min-h-0 flex-col sm:flex-row">
      {/* gruppert side-nav — SkillsPage-idiomet (sticky kolonne, mondwest-etiketter) */}
      <aside className="sm:w-52 sm:shrink-0 sm:overflow-y-auto border-b sm:border-b-0 sm:border-r border-border">
        <div className="flex sm:flex-col gap-0.5 overflow-x-auto sm:overflow-x-visible p-2">
          {groups.map((g) => (
            <div key={g.title} className="sm:mb-2">
              <div className="hidden sm:block px-2 pb-1 pt-2 font-mondwest text-display text-[10px] tracking-[0.12em] text-text-tertiary">
                {g.title}
              </div>
              <div className="flex sm:flex-col gap-0.5">
                {g.tabs.map((t) => {
                  const Icon = t.icon;
                  const on = t.id === tab.id;
                  return (
                    <button
                      key={t.id}
                      onClick={() => select(t.id)}
                      title={t.hint}
                      className={
                        "flex shrink-0 items-center gap-2 px-2 py-1 text-left text-xs transition-colors " +
                        (on
                          ? "bg-muted/40 font-medium text-foreground"
                          : "text-muted-foreground hover:text-foreground")
                      }
                    >
                      <Icon className="h-3.5 w-3.5 shrink-0" />
                      <span className="truncate">{t.label}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </aside>
      <div className="min-h-0 min-w-0 flex-1 overflow-auto">
        <div className="border-b border-border px-4 py-2 text-xs text-muted-foreground">
          {pendingDyn ? "henter domene-registeret …" : tab.hint}
        </div>
        {pendingDyn ? (
          <div className="p-6 text-sm text-muted-foreground">henter domene-registeret …</div>
        ) : (
          tab.render()
        )}
      </div>
    </div>
  );
}
