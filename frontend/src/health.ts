export type HealthState = "checking" | "ok" | "down";

export function healthLabel(state: HealthState): string {
  switch (state) {
    case "checking":
      return "Checking backend…";
    case "ok":
      return "Backend is up";
    case "down":
      return "Backend is not reachable";
  }
}

export async function fetchHealth(): Promise<HealthState> {
  try {
    const response = await fetch("/api/health");
    const body = (await response.json()) as { status?: string };
    return response.ok && body.status === "ok" ? "ok" : "down";
  } catch {
    return "down";
  }
}
