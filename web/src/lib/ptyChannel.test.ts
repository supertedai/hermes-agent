import { describe, expect, it } from "vitest";

import { stablePtyChannelId } from "./ptyChannel";

const TOKEN = "9f2c1d0e8b7a65543210fedcba987654";

describe("stablePtyChannelId", () => {
  it("is deterministic across calls (remount/refresh must resubscribe to the PTY's channel)", () => {
    const a = stablePtyChannelId(TOKEN, "sess_123", "worker");
    const b = stablePtyChannelId(TOKEN, "sess_123", "worker");
    expect(a).toBe(b);
  });

  it("emits the documented shape: chat- prefix + 16 hex chars", () => {
    expect(stablePtyChannelId(TOKEN, "", "")).toMatch(/^chat-[0-9a-f]{16}$/);
  });

  it("rotates with the attach token (fresh start → fresh channel)", () => {
    const before = stablePtyChannelId(TOKEN, "", "");
    const after = stablePtyChannelId("00112233445566778899aabbccddeeff", "", "");
    expect(after).not.toBe(before);
  });

  it("separates resume and profile scopes", () => {
    const base = stablePtyChannelId(TOKEN, "", "");
    expect(stablePtyChannelId(TOKEN, "sess_123", "")).not.toBe(base);
    expect(stablePtyChannelId(TOKEN, "", "worker")).not.toBe(base);
  });

  it("does not collide when content shifts across the field boundary", () => {
    // ("ab", "c") vs ("a", "bc") — the NUL separator must keep these apart.
    const left = stablePtyChannelId(TOKEN, "ab", "c");
    const right = stablePtyChannelId(TOKEN, "a", "bc");
    expect(left).not.toBe(right);
  });

  it("never leaks the raw attach token into the channel name", () => {
    expect(stablePtyChannelId(TOKEN, "", "")).not.toContain(TOKEN);
  });
});
