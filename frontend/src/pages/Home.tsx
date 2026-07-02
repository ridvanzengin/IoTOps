import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fetchHealth } from "../api/health";

export function Home() {
  const [backendStatus, setBackendStatus] = useState<"checking" | "ok" | "unreachable">("checking");

  useEffect(() => {
    fetchHealth()
      .then((health) => setBackendStatus(health.status === "ok" ? "ok" : "unreachable"))
      .catch(() => setBackendStatus("unreachable"));
  }, []);

  return (
    <main className="page">
      <h1>IoTOps</h1>
      <p style={{ marginTop: 8, marginBottom: 24 }}>
        Self-hosted IoT operations platform. Configure telemetry collectors, and soon,
        automation rules and dashboards, without hand-writing config files.
      </p>

      <div className="status-card">
        <span>Backend</span>
        <span className={`status-dot status-dot--${backendStatus}`} />
        <span>{backendStatus}</span>
      </div>

      <p style={{ marginTop: 24 }}>
        <Link className="button" to="/collectors">
          Go to Collectors
        </Link>
      </p>
    </main>
  );
}
