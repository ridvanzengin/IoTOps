import { useDemoMode } from "../context/DemoModeContext";
import "./Toast.css";

export function Toast() {
  const { toastMessage, dismissToast } = useDemoMode();

  if (!toastMessage) return null;

  return (
    <div className="toast" role="status">
      <span>{toastMessage}</span>
      <button type="button" className="toast__dismiss" onClick={dismissToast} aria-label="Dismiss">
        ×
      </button>
    </div>
  );
}
