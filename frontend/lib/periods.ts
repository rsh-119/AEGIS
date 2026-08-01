/** Shared chart-period options — was independently duplicated across
 * stock/index/market/sector pages. `PERIODS_BASIC` omits "All", matching
 * the market/sector pages' existing (narrower) history range. */
export const PERIODS = [
  { label: "1M", value: "1mo" },
  { label: "3M", value: "3mo" },
  { label: "6M", value: "6mo" },
  { label: "1Y", value: "1y" },
  { label: "2Y", value: "2y" },
  { label: "5Y", value: "5y" },
  { label: "All", value: "max" },
];

export const PERIODS_BASIC = PERIODS.slice(0, -1);
