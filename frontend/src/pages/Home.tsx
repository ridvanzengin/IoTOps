import { useEffect, useState } from "react";
import { fetchHealth } from "../api/health";

export function Home() {
  const [backendStatus, setBackendStatus] = useState<"checking" | "ok" | "unreachable">("checking");

  useEffect(() => {
    fetchHealth()
      .then((health) => setBackendStatus(health.status === "ok" ? "ok" : "unreachable"))
      .catch(() => setBackendStatus("unreachable"));
  }, []);

  return (
    <main>
      <h1>IoTOps</h1>
      <p>Backend status: {backendStatus}</p>
    </main>
  );
}
