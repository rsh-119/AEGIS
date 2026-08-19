// lib/calculator.ts — forward-looking projection math (SIP future value,
// lumpsum compound interest). Pure functions, no data dependency — shared
// between components/ProjectionCalculator.tsx (stock page + standalone
// /calculator page) so the formula lives in exactly one place.

export type Projection = { invested: number; value: number; gain: number };

/** SIP future value — annuity due (investment at the start of each month),
 * monthly compounding. Standard formula used by Indian SIP calculators. */
export function projectSip(monthlyAmount: number, years: number, annualRatePct: number): Projection {
  const i = annualRatePct / 100 / 12;
  const n = Math.round(years * 12);
  const invested = monthlyAmount * n;
  const value = i === 0 ? invested : monthlyAmount * (((Math.pow(1 + i, n) - 1) / i) * (1 + i));
  return { invested, value, gain: value - invested };
}

/** Lumpsum future value — standard compound interest. */
export function projectLumpsum(amount: number, years: number, annualRatePct: number): Projection {
  const value = amount * Math.pow(1 + annualRatePct / 100, years);
  return { invested: amount, value, gain: value - amount };
}
