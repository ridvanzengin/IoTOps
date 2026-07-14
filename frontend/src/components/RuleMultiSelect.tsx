import { useEffect, useRef, useState } from "react";
import "./RuleMultiSelect.css";

export interface RuleOption {
  id: string;
  name: string;
  // Which Automater a real-time Rule belongs to, or "Scheduled" for a
  // Query Rule -- generic label, not automater-specific, since this list
  // spans both rule kinds. See iotops-workspace/ROADMAP.md's "Query
  // Rules" note.
  sourceLabel: string;
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

  // Counts (and names, for the tooltip) only ids that resolve to a rule
  // actually in `rules` today -- `selectedIds` is the panel's raw stored
  // event_rule_ids, which can outlive the Rule/Query Rule it once pointed
  // to (deleting one doesn't clean up any Panel referencing it). Counting
  // the raw array length would show e.g. "3 selected" while only 2
  // checkboxes are actually checkable/checked. A fixed "Events (N)" label
  // regardless of count, rather than switching to a rule's own name at
  // count 1, so the trigger doesn't reflow/change shape as the selection changes.
  const resolvedNames = selectedIds
    .map((id) => rules.find((r) => r.id === id)?.name)
    .filter((name): name is string => Boolean(name));
  const label = resolvedNames.length > 0 ? `Events (${resolvedNames.length})` : "Events";

  return (
    <div className={`rule-multiselect ${compact ? "rule-multiselect--compact" : ""}`} ref={containerRef}>
      <button
        type="button"
        className="rule-multiselect__trigger"
        onClick={() => setOpen((value) => !value)}
        disabled={rules.length === 0}
        title={resolvedNames.length > 0 ? `Overlaying: ${resolvedNames.join(", ")}` : "Overlay events"}
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
                      <span className="rule-multiselect__automater"> · {rule.sourceLabel}</span>
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
