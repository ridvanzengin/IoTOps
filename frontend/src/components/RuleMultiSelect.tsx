import { useEffect, useRef, useState } from "react";
import "./RuleMultiSelect.css";

export interface RuleOption {
  id: string;
  name: string;
  automaterName: string;
}

interface RuleMultiSelectProps {
  rules: RuleOption[];
  selectedIds: string[];
  onChange: (ids: string[]) => void;
  // Icon-sized trigger for the dashboard panel header (next to the
  // "..." menu) instead of the full-width form-field look.
  compact?: boolean;
}

// A multi-select dropdown of specific Rules, for the Panel-overlay
// feature -- see iotops-workspace/ROADMAP.md's "Events-as-overlay on
// Panel charts" note. Deliberately Rule, not event_type/category (those
// are free text nothing enforces consistency on); lists every Rule in
// the project, not table-filtered (a panel's query can join tables, so
// there's no single table to match against).
export function RuleMultiSelect({ rules, selectedIds, onChange, compact = false }: RuleMultiSelectProps) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  function toggle(id: string) {
    onChange(selectedIds.includes(id) ? selectedIds.filter((x) => x !== id) : [...selectedIds, id]);
  }

  const selectedRule = selectedIds.length === 1 ? rules.find((r) => r.id === selectedIds[0]) : null;
  const label =
    selectedIds.length === 0
      ? compact
        ? "Events"
        : "None"
      : selectedIds.length === 1
        ? (selectedRule?.name ?? "1 selected")
        : `${selectedIds.length} selected`;

  return (
    <div className={`rule-multiselect ${compact ? "rule-multiselect--compact" : ""}`} ref={containerRef}>
      <button
        type="button"
        className="rule-multiselect__trigger"
        onClick={() => setOpen((value) => !value)}
        disabled={rules.length === 0}
        title={selectedIds.length > 0 ? `Overlaying: ${selectedIds.map((id) => rules.find((r) => r.id === id)?.name ?? id).join(", ")}` : "Overlay events"}
      >
        <span className="rule-multiselect__trigger-label">{label}</span>
        <span className="rule-multiselect__trigger-caret">▾</span>
      </button>
      {open && (
        <div className="rule-multiselect__panel">
          {rules.length === 0 ? (
            <p className="rule-multiselect__empty">No rules in this project.</p>
          ) : (
            <ul className="rule-multiselect__list">
              {rules.map((rule) => (
                <li key={rule.id}>
                  <label className="rule-multiselect__option">
                    <input type="checkbox" checked={selectedIds.includes(rule.id)} onChange={() => toggle(rule.id)} />
                    <span className="rule-multiselect__option-label">
                      {rule.name}
                      <span className="rule-multiselect__automater"> · {rule.automaterName}</span>
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
