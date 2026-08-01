// symbioseTheme.ts — Symbiose-fanene skal snakke HERMES' designspråk, ikke :8910s.
//
// Morten (2026-07-23): «vi må ha en stil/theme som er likt Hermes GUI på alt her nå».
// Første Executive-versjon arvet :8910-estetikken (fargede venstre-kanter, rå
// tailwind-farger som emerald/sky). Dette modulet er den ENE oversettelsen fra
// dashboardets statusfarger til Hermes' egne tokens — definert her, aldri i sidene:
//
//   HERMES-IDIOMET (lest ut av SkillsPage/PluginsPage/AnalyticsPage):
//   - Skarpe hjørner: aldri rounded-* på paneler/badges.
//   - Paneler: border border-border bg-background/20 (sub-blokker /40).
//   - Seksjonsetiketter: font-mondwest text-display text-xs tracking-[0.12em].
//   - Status: text-success/-warning/-destructive/-primary + /10-tinter og /50-kanter
//     (theme-tokens — følger lys/mørk automatisk; rå palettfarger gjør ikke det).
//
// :8910-fargene {green, amber, red, blue, grey} mappes hit og BARE hit.

export const PANEL = "border border-border bg-background/20";
export const SUBPANEL = "border border-border bg-background/40";
export const SECTION_LABEL =
  "font-mondwest text-display text-xs tracking-[0.12em] text-text-secondary";

export const TONE_TEXT: Record<string, string> = {
  green: "text-success",
  amber: "text-warning",
  red: "text-destructive",
  blue: "text-primary",
  grey: "text-muted-foreground",
};

// Badge-idiomet fra PluginsPage.setupResultClass: farget /50-kant + farget tekst.
export const TONE_BADGE: Record<string, string> = {
  green: "border-success/50 text-success",
  amber: "border-warning/50 text-warning",
  red: "border-destructive/50 text-destructive",
  blue: "border-primary/50 text-primary",
  grey: "border-border text-muted-foreground",
};

export const TONE_DOT: Record<string, string> = {
  green: "bg-success",
  amber: "bg-warning",
  red: "bg-destructive",
  blue: "bg-primary",
  grey: "bg-muted-foreground/40",
};

export const TONE_TINT: Record<string, string> = {
  green: "bg-success/10",
  amber: "bg-warning/10",
  red: "bg-destructive/10",
  blue: "bg-primary/10",
  grey: "bg-muted/20",
};

export function toneText(c: string | undefined): string {
  return TONE_TEXT[c ?? "grey"] ?? TONE_TEXT.grey;
}
export function toneBadge(c: string | undefined): string {
  return TONE_BADGE[c ?? "grey"] ?? TONE_BADGE.grey;
}
export function toneDot(c: string | undefined): string {
  return TONE_DOT[c ?? "grey"] ?? TONE_DOT.grey;
}
export function toneTint(c: string | undefined): string {
  return TONE_TINT[c ?? "grey"] ?? TONE_TINT.grey;
}
