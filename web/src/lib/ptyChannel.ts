/**
 * ptyChannel — stable event-channel identity for the dashboard Chat tab
 * (BL-2563, follow-up to BL-2555).
 *
 * The channel id ties three legs together: the PTY child publishes every
 * dispatcher emit to /api/pub?channel=…, the dashboard rebroadcasts to
 * /api/events?channel=…, and ChatSidebar subscribes there for its tool feed
 * and agent-flow chips.
 *
 * The PTY child gets the channel baked into HERMES_TUI_SIDECAR_URL at spawn
 * and can never change it. The keep-alive registry reattaches a refreshed tab
 * to that same living PTY — so a channel generated fresh per mount (the old
 * scheme) desynced on the first refresh: the PTY kept publishing to the spawn
 * channel while the remounted sidebar subscribed to a new one, and the whole
 * event feed (chips included) went dark even though the terminal worked.
 *
 * Fix: derive the channel deterministically from the SAME inputs that select
 * the PTY (attach token + resume target + profile scope). Any mount that
 * reattaches to a given PTY then also subscribes to the channel that PTY
 * publishes on; rotating the attach token (explicit fresh start) rotates the
 * channel with it.
 *
 * Known corner: /api/pty canonicalises an explicit ?resume= id server-side
 * (HERMES_TUI_RESUME), so two DIFFERENT resume ids that canonicalise to the
 * same session share a PTY but derive different channels. That mount's feed
 * stays quiet until the next fresh start — same blast radius as the old
 * scheme's every-refresh desync, now confined to a rare alias case.
 *
 * The hash is FNV-1a (two 32-bit lanes → 16 hex chars). Not cryptographic —
 * it doesn't need to be: channel names were never a secret (they ride in
 * query strings and the PTY child's env), all three WebSocket legs require
 * dashboard auth, and 128 bits of attach-token entropy cannot be recovered
 * from a 64-bit digest.
 */

const FNV_OFFSET = 0x811c9dc5;
const FNV_PRIME = 0x01000193;

function fnv1a32(input: string, seed: number): number {
  let h = (FNV_OFFSET ^ seed) >>> 0;
  for (let i = 0; i < input.length; i++) {
    h ^= input.charCodeAt(i);
    h = Math.imul(h, FNV_PRIME) >>> 0;
  }
  return h >>> 0;
}

/**
 * Deterministic channel id for a chat tab's PTY identity.
 *
 * Same (attachToken, resume, profile) → same channel, across remounts,
 * refreshes, and devices sharing the token. Empty-able inputs are folded in
 * with a separator that cannot occur in any of them, so ("ab", "c") never
 * collides with ("a", "bc").
 */
export function stablePtyChannelId(
  attachToken: string,
  resume: string,
  profile: string,
): string {
  const scope = `${attachToken}\0${resume}\0${profile}`;
  const hi = fnv1a32(scope, 0);
  const lo = fnv1a32(scope, 0x9e3779b9);
  const hex = (n: number) => n.toString(16).padStart(8, "0");
  return `chat-${hex(hi)}${hex(lo)}`;
}
