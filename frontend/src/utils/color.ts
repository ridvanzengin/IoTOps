// Deterministic id -> color, same fallback-avatar pattern Slack/GitHub use
// for entities with no dedicated color field (no schema change needed on
// Project/Rule). Originally lived in ActivityBar.tsx for project badges;
// pulled out here so OccurrenceCard and EventsPanel's rule filter chips can
// hash the same rule_id to the same color and actually look connected --
// see iotops-workspace/ROADMAP.md's "Events sidebar polish" note. Distinct
// from the severity scale in index.css and from CHART_COLORS (a 6-hue
// chart-series palette tuned for dark chart surfaces/stroke contrast --
// wrong lightness/chroma band for a solid badge fill or border accent on
// this app's light UI, confirmed by running it through the same validator
// below).
//
// This 8-hue set is the dataviz skill's validated reference categorical
// palette (references/palette.md), *not* hand-picked -- the previous
// palette here read as arbitrary because one slot (#0f766e) failed the
// chroma floor (too desaturated/gray relative to the rest) despite
// technically-fine hue separation, which is exactly the kind of thing
// that makes a palette look "random" even when no two colors are
// literally identical. Verified via:
//   node scripts/validate_palette.js "<hexes>" --mode light
// against this app's light surface -- lightness band, chroma floor, and
// CVD separation (worst adjacent ΔE 24.2, well above the 12 floor) all
// pass. Three slots warn below 3:1 contrast as a bare fill; every actual
// use here (badge initials, chip/card rule name) already pairs the color
// with a text label, which is the prescribed mitigation, not optional.
const PALETTE = [
  "#2a78d6", // blue
  "#1baf7a", // aqua
  "#eda100", // yellow
  "#008300", // green
  "#4a3aa7", // violet
  "#e34948", // red
  "#e87ba4", // magenta
  "#eb6834", // orange
];

export function hashColor(id: string, palette: readonly string[] = PALETTE): string {
  let hash = 0;
  for (let i = 0; i < id.length; i++) {
    hash = (hash * 31 + id.charCodeAt(i)) >>> 0;
  }
  return palette[hash % palette.length];
}

// Same fallback-avatar pattern as hashColor -- paired with it wherever a
// name-bearing entity (Project, initially) needs an avatar with no
// dedicated image.
export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
}
