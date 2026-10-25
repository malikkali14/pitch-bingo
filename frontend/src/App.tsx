import { useEffect, useState } from "react";
import { fetchHealth, healthLabel, type HealthState } from "./health";

// Placeholder page for phase 1. The real screen arrives in phase 5 (spec section 3).
export default function App() {
  const [health, setHealth] = useState<HealthState>("checking");

  useEffect(() => {
    fetchHealth().then(setHealth);
  }, []);

  return (
    <main style={{ fontFamily: "system-ui, sans-serif", padding: "2rem" }}>
      <h1>Pitch Bingo</h1>
      <p data-testid="health">{healthLabel(health)}</p>
    </main>
  );
}
