import type { WagePercentiles } from "@/lib/types";

/**
 * Two wage distributions on one scale, drawn as server-rendered SVG.
 *
 * The table this sits beside gives six numbers and asks the reader to hold them in mind and
 * subtract. Its actual finding — that a region is not uniformly lower than the state but
 * differently shaped, wider here and shifted there — is a comparison of intervals, and an
 * interval is the one thing a row of figures is genuinely bad at conveying. That is the
 * argument for a chart here and it is not an argument for charts generally: the numbers
 * elsewhere on this site are single quantities, and a bar of one number is decoration.
 *
 * No library, no client JavaScript, no canvas. It is markup, so it renders with scripting
 * off, survives being printed, costs nothing to download, and cannot disagree with the table
 * beside it because both read the same props.
 *
 * `aria-hidden`, deliberately. The table immediately below carries every value with proper
 * headers; announcing the same figures twice makes a screen reader's version of this page
 * worse, not better. A chart that duplicates an accessible table should get out of the way.
 */

/*
 * Labels sit above their bars, not beside them.
 *
 * Beside them needs a fixed label column, and the labels here are published area names —
 * "Los Angeles-Long Beach-Glendale MD (Los Angeles County)" is fifty-three characters. Any
 * column narrow enough to leave a usable plot is too narrow for the names, and SVG text does
 * not wrap or clip: it simply drew straight through the bar. Stacking removes the constraint
 * rather than trading one bad width for another.
 */
const WIDTH = 640;
const LABEL_HEIGHT = 17;
const BAR_HEIGHT = 12;
const ROW_GAP = 16;
const ROW_HEIGHT = LABEL_HEIGHT + BAR_HEIGHT + ROW_GAP;
const PLOT_INSET = 2;

export interface WageRangeRow {
  label: string;
  percentiles: WagePercentiles;
  emphasis?: boolean;
}

export function WageRangeChart({ rows }: { rows: readonly WageRangeRow[] }) {
  /*
   * Only rows whose whole interval was published. A bar drawn from a suppressed tenth
   * percentile would have to start somewhere, and wherever it started would be this project
   * inventing the number the Bureau withheld — in a form the reader cannot tell apart from a
   * measurement. The table keeps the partial rows; the chart declines to draw them.
   */
  const usable = rows.filter(
    (row) =>
      row.percentiles.p10 !== null &&
      row.percentiles.p50 !== null &&
      row.percentiles.p90 !== null,
  );
  if (usable.length === 0) return null;

  const lows = usable.map((r) => r.percentiles.p10 as number);
  const highs = usable.map((r) => r.percentiles.p90 as number);
  const min = Math.min(...lows);
  const max = Math.max(...highs);
  const span = max - min;
  // Every row identical, or a single point: a scale of zero width has no shape to show.
  if (span <= 0) return null;

  const plot = WIDTH - PLOT_INSET * 2;
  const x = (value: number) => PLOT_INSET + ((value - min) / span) * plot;
  const height = usable.length * ROW_HEIGHT;

  return (
    <svg
      aria-hidden="true"
      className="wage-chart"
      focusable="false"
      viewBox={`0 0 ${WIDTH} ${height}`}
      role="presentation"
    >
      {usable.map((row, index) => {
        const p = row.percentiles;
        const top = index * ROW_HEIGHT;
        const y = top + LABEL_HEIGHT;
        const hasQuartiles = p.p25 !== null && p.p75 !== null;
        return (
          <g key={row.label}>
            <text className="wage-chart-label" x={0} y={top + 12}>
              {row.label}
            </text>
            {/* Tenth to ninetieth: the full published interval. */}
            <rect
              className={`wage-chart-range${row.emphasis ? " is-emphasis" : ""}`}
              x={x(p.p10 as number)}
              y={y}
              width={Math.max(1, x(p.p90 as number) - x(p.p10 as number))}
              height={BAR_HEIGHT}
              rx={2}
            />
            {/* The middle half, drawn only when both quartiles exist. */}
            {hasQuartiles && (
              <rect
                className={`wage-chart-mid${row.emphasis ? " is-emphasis" : ""}`}
                x={x(p.p25 as number)}
                y={y}
                width={Math.max(1, x(p.p75 as number) - x(p.p25 as number))}
                height={BAR_HEIGHT}
                rx={2}
              />
            )}
            <line
              className="wage-chart-median"
              x1={x(p.p50 as number)}
              x2={x(p.p50 as number)}
              y1={y - 3}
              y2={y + BAR_HEIGHT + 3}
            />
          </g>
        );
      })}
    </svg>
  );
}
