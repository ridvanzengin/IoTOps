import type { PanelPosition } from "../types/dashboard";

export const DEFAULT_POSITION: PanelPosition = { x: 0, y: 0, width: 6, height: 8 };
const GRID_COLUMNS = 12;

// Structural, not `Panel[]` -- CopilotChat.tsx's dashboard-suggestion
// bulk-create folds this over plain `{ position }` placeholders for
// panels that don't exist as real `Panel`s yet (no id/chart/query needed
// just to reserve a grid slot), while PanelBuilder.tsx passes real
// `Panel[]` from an already-persisted dashboard -- both satisfy this.
interface PositionedPanel {
  position: PanelPosition;
}

function positionsOverlap(a: PanelPosition, b: PanelPosition): boolean {
  return (
    a.x < b.x + b.width &&
    a.x + a.width > b.x &&
    a.y < b.y + b.height &&
    a.y + a.height > b.y
  );
}

// First-fit shelf packing: try each existing row (y = 0, or just below any
// panel) left-to-right before falling back to a new row underneath
// everything, so a new panel lands in an empty slot beside existing panels
// rather than always starting a fresh row. Shared by PanelBuilder.tsx (one
// panel at a time, against a dashboard's real persisted panels) and
// CopilotChat.tsx's dashboard-suggestion bulk-create (several panels at
// once, folded over an initially-empty array so each successive panel
// accounts for the ones already placed earlier in the same batch).
export function findFreePosition(panels: PositionedPanel[], width: number, height: number): PanelPosition {
  const candidateYs = [0, ...panels.map((panel) => panel.position.y + panel.position.height)];
  const sortedYs = Array.from(new Set(candidateYs)).sort((a, b) => a - b);

  for (const y of sortedYs) {
    for (let x = 0; x + width <= GRID_COLUMNS; x++) {
      const candidate: PanelPosition = { x, y, width, height };
      if (!panels.some((panel) => positionsOverlap(candidate, panel.position))) {
        return candidate;
      }
    }
  }

  const bottom = panels.reduce((max, panel) => Math.max(max, panel.position.y + panel.position.height), 0);
  return { x: 0, y: bottom, width, height };
}
