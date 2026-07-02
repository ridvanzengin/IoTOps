import type { CollectorStatus } from "../types/collector";

const STATUS_LABEL: Record<CollectorStatus, string> = {
  created: "Created",
  stopped: "Stopped",
  starting: "Starting",
  running: "Running",
  unhealthy: "Unhealthy",
  stopping: "Stopping",
  error: "Error",
};

export function StatusBadge({ status }: { status: CollectorStatus }) {
  return <span className={`status-badge status-badge--${status}`}>{STATUS_LABEL[status]}</span>;
}
