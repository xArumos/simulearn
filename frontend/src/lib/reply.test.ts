import { describe, expect, it } from "vitest";
import { ageLabel, isSilentReply, replyParts, thinkingDelayMs } from "@/lib/reply";

describe("replyParts", () => {
  it("keeps plain text as one part", () => {
    expect(replyParts("i made a big tower")).toEqual([{ kind: "text", text: "i made a big tower" }]);
  });

  it("turns a leading silence tag into a pause part", () => {
    expect(replyParts("<SILENCE FOR 3 SECONDS> um the red one")).toEqual([
      { kind: "pause", seconds: 3 },
      { kind: "text", text: "um the red one" },
    ]);
  });

  it("handles pauses in the middle and several tags", () => {
    expect(replyParts("yeah <SILENCE FOR 2 SECONDS> and then <SILENCE FOR 10 SECONDS>")).toEqual([
      { kind: "text", text: "yeah" },
      { kind: "pause", seconds: 2 },
      { kind: "text", text: "and then" },
      { kind: "pause", seconds: 10 },
    ]);
  });

  it("never leaves the raw tag in a text part", () => {
    const parts = replyParts("<SILENCE FOR 4 SECONDS>no<SILENCE FOR 2 SECONDS>");
    expect(parts.filter((p) => p.kind === "text").map((p) => (p as { text: string }).text)).toEqual(["no"]);
  });

  it("returns nothing for an empty reply", () => {
    expect(replyParts("   ")).toEqual([]);
    expect(isSilentReply("")).toBe(true);
    expect(isSilentReply("<SILENCE FOR 5 SECONDS>")).toBe(true);
    expect(isSilentReply("<SILENCE FOR 5 SECONDS> no")).toBe(false);
  });
});

describe("thinkingDelayMs", () => {
  it("waits the pause length, capped at 5 seconds", () => {
    expect(thinkingDelayMs(3)).toBe(3000);
    expect(thinkingDelayMs(5)).toBe(5000);
    expect(thinkingDelayMs(9)).toBe(5000);
  });

  it("does not wait without a pause", () => {
    expect(thinkingDelayMs(null)).toBe(0);
    expect(thinkingDelayMs(undefined)).toBe(0);
    expect(thinkingDelayMs(0)).toBe(0);
  });
});

describe("ageLabel", () => {
  it("adds the config label in brackets", () => {
    expect(ageLabel(5, "60-71 months")).toBe("5 years (60-71 months)");
  });
  it("falls back to the years alone", () => {
    expect(ageLabel(4, "")).toBe("4 years");
    expect(ageLabel(4)).toBe("4 years");
  });
});
