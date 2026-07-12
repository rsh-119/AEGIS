# AEGIS visual & motion overhaul — change summary

## Typography
- **Display face: Fraunces** (high-contrast serif, weights 400–600) wired through
  the existing `--font-display` variable / `font-display` Tailwind family, so it
  applies to the hero, all section headings, showcase titles, stats numerals,
  bento card titles, and the AEGIS wordmark in Nav/Footer. Inter stays for body,
  IBM Plex Mono for numbers/eyebrows.
- **Fluid heading scale** — hero and section headings use `clamp()`
  (`clamp(3rem, 7.5vw, 5.25rem)` hero; `clamp(2rem, 4.5vw, 3rem)` sections) so
  type scales smoothly between breakpoints instead of jumping.
- Serif-appropriate tracking (`-0.015em`/`-0.02em`, was tighter for the grotesque).
- Eyebrow style (mono, 10.5px, letter-spaced uppercase, saffron) applied to every
  section kicker; `.nums` (tabular figures) on all price/percent/currency figures.

## Motion system — `components/motion/`
- `Reveal.tsx` — scroll-triggered fade + 26px rise (IntersectionObserver,
  once-only, fires slightly before entry). Compositor-only (opacity/transform),
  shared easing `cubic-bezier(0.16, 1, 0.3, 1)`. Its `.reveal-visible` class also
  drives the in-mock micro-animations.
- `Stagger.tsx` — wraps children in incrementally-delayed Reveals (used on the
  stats strip).
- `MotionNumber.tsx` — counts up on first view (easeOutQuart, no bounce), used
  for "5,000+" and the portfolio mock's ₹12,40,318.
- `ScrollProgress.tsx` — 2px saffron scroll-progress bar fixed above the nav
  (scroll-linked via framer-motion, hidden under reduced motion).
- (Pre-existing from this design pass, kept: hero word-by-word blur-in stagger,
  showcase panel scroll-parallax, keyword marquee, floating accent chips.)

## Hero
- Aurora background (animated drifting gradient ribbons) + new grain overlay
  (`.noise`) so gradients don't band.
- Headline word-stagger entrance; trending chips get magnetic hover
  (scale + lift + border brighten).

## Hover & micro-interactions
- **Cursor spotlight** (`.spotlight-layer`) — a saffron radial highlight follows
  the pointer inside bento cards and showcase panels via `--sx`/`--sy` CSS vars.
- **Button sheen** (`.btn-sheen`) — light band sweeps across the primary CTA on
  hover; `active:scale-[0.98]` press-down.
- Bento tiles: existing lift/border/shadow hover, plus the mini-visuals now
  respond — peer ROE bars grow (`scale-x`), alert and watchlist rows shift right.
- Nav already had scroll-reactive glass + active states (kept).

## Section motion graphics
- Market mock: sparkline self-draws on reveal (stroke-dashoffset, pre-existing);
  the +1.02% badge gets a soft periodic `tick-pulse` like a refreshing quote.
- Portfolio mock: allocation bar segments grow from zero, staggered
  (pre-existing); portfolio value counts up via MotionNumber.
- Concall mock: the three AI bullets stagger in (`.brief-li`) after the panel
  reveals.
- Workflow rows reveal sequentially with hover states (pre-existing).

## New CSS utilities/tokens (globals.css)
`.spotlight-layer`, `.btn-sheen`, `.tick-pulse`, `.brief-li` (+ keyframes
`tick-pulse`, `brief-in`), grain via existing `.noise`. All colors via existing
tokens — no hardcoded hexes. Every new animation has an explicit
`prefers-reduced-motion` reset (delays survive the global duration clamp, so
final states are forced).

## Bug fix (functional, shipped alongside)
`mutate` imported from `"swr"` targets the default cache, but the app runs a
custom IDB-backed provider — so portfolio/watchlist/alert mutations never
revalidated until a reload. Switched to provider-bound `useSWRConfig().mutate`
in `app/portfolio`, `app/watchlist`, `app/alerts`, and `lib/useWatchlist`.

## Verification
- `npm run build` clean (dev server stopped first — concurrent build+dev
  corrupts `.next`).
- Playwright full-page screenshots at 1440px and 375px, light and dark, reviewed:
  no horizontal overflow at either width, no console/page errors.
