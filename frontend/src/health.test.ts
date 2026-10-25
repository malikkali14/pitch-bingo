import { describe, expect, it } from "vitest";
import { healthLabel } from "./health";

describe("healthLabel", () => {
  it("describes each state", () => {
    expect(healthLabel("checking")).toBe("Checking backend…");
    expect(healthLabel("ok")).toBe("Backend is up");
    expect(healthLabel("down")).toBe("Backend is not reachable");
  });
});
