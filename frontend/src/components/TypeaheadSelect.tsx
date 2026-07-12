import { useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import "./TypeaheadSelect.css";

interface TypeaheadSelectProps {
  options: string[];
  value: string;
  onChange: (value: string) => void;
  className?: string;
  placeholder?: string;
}

// Filterable dropdown for variable selectors that can have many resolved
// options (e.g. every device_id in a table) -- a plain <select> forces
// scrolling through the whole list. A button trigger shows the current
// value; opening it reveals a panel with a search input pinned at the
// top and the (live-filtered) option list directly beneath it -- not a
// native <datalist> (its suggestions can't be constrained to only the
// given options, so a user could submit arbitrary typed text), and not
// a new dependency -- a dashboard variable value must always be one of
// the actual resolved options, so selection is enforced here, in-house.
export function TypeaheadSelect({ options, value, onChange, className, placeholder }: TypeaheadSelectProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [highlightedIndex, setHighlightedIndex] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  const filteredOptions = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return options;
    return options.filter((option) => option.toLowerCase().includes(q));
  }, [options, query]);

  useEffect(() => {
    setHighlightedIndex(0);
  }, [filteredOptions.length, open]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
        setQuery("");
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  function openDropdown() {
    setOpen(true);
    setQuery("");
    // The search input isn't mounted until `open` flips true -- focus it
    // on the next paint rather than fighting the not-yet-rendered ref.
    requestAnimationFrame(() => searchRef.current?.focus());
  }

  function commit(option: string) {
    onChange(option);
    setQuery("");
    setOpen(false);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setHighlightedIndex((i) => Math.min(i + 1, filteredOptions.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setHighlightedIndex((i) => Math.max(i - 1, 0));
    } else if (event.key === "Enter") {
      event.preventDefault();
      const option = filteredOptions[highlightedIndex];
      if (option) commit(option);
    } else if (event.key === "Escape") {
      setOpen(false);
      setQuery("");
    }
  }

  return (
    <div className="typeahead" ref={containerRef}>
      <button
        type="button"
        className={`typeahead__trigger ${className ?? ""}`}
        onClick={() => (open ? setOpen(false) : openDropdown())}
      >
        <span className="typeahead__trigger-label">{value || placeholder || "Select..."}</span>
        <span className="typeahead__trigger-caret">▾</span>
      </button>
      {open && (
        <div className="typeahead__panel">
          <input
            ref={searchRef}
            type="text"
            className="typeahead__search"
            placeholder="Type to filter..."
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={handleKeyDown}
          />
          <ul className="typeahead__list">
            {filteredOptions.length === 0 ? (
              <li className="typeahead__empty">No matches</li>
            ) : (
              filteredOptions.map((option, index) => (
                <li key={option}>
                  <button
                    type="button"
                    className={`typeahead__option ${option === value ? "typeahead__option--selected" : ""} ${
                      index === highlightedIndex ? "typeahead__option--highlighted" : ""
                    }`}
                    onMouseDown={(event) => {
                      // Keep the search input focused (avoid a
                      // blur-before-click race closing the panel first).
                      event.preventDefault();
                      commit(option);
                    }}
                    onMouseEnter={() => setHighlightedIndex(index)}
                  >
                    {option}
                  </button>
                </li>
              ))
            )}
          </ul>
        </div>
      )}
    </div>
  );
}
