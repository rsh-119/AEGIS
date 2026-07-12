import type { Config } from "tailwindcss";

const c  = (v: string) => `rgb(var(${v}) / <alpha-value>)`;
const cv = (v: string) => `rgb(var(${v}) / <alpha-value>)`;

const config: Config = {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        /* ── Core tokens (unchanged names — existing components keep working) ── */
        ink:     c("--color-ink"),        /* page floor         */
        surface: c("--color-surface"),    /* card face / canvas */
        raised:  c("--color-raised"),     /* inputs, chips      */
        border:  c("--color-border"),     /* hairline           */
        muted:   c("--color-muted"),      /* secondary text     */
        fg:      c("--color-fg"),         /* body text (ink)    */

        /* saffron token now maps to indigo #533afd — zero JSX changes needed */
        saffron: c("--color-saffron"),    /* primary indigo CTA */
        accent:  c("--color-accent"),     /* ruby               */
        up:      c("--color-up"),
        down:    c("--color-down"),

        /* ── Stripe extended palette ─────────────────────────────────────── */
        primary:      c("--color-saffron"),          /* alias for indigo CTA */
        "canvas-soft": cv("--color-canvas-soft"),
        "canvas-cream": cv("--color-canvas-cream"),
        "ink-secondary": cv("--color-ink-secondary"),
        "ink-mute":   cv("--color-ink-mute"),
        "brand-dark": cv("--color-brand-dark"),      /* #1c1e54 dark tier    */
      },

      fontFamily: {
        sans:    ["var(--font-sans)", "system-ui", "sans-serif"],
        display: ["var(--font-display)", "var(--font-sans)", "system-ui", "sans-serif"],
        mono:    ["var(--font-mono)", "ui-monospace", "monospace"],
      },

      fontSize: {
        /* Display tier — Coinbase scale, weight 400 (never bold), negative tracking */
        "display-xxl": ["80px", { lineHeight: "1.0",  letterSpacing: "-2px",   fontWeight: "400" }],
        "display-xl":  ["64px", { lineHeight: "1.0",  letterSpacing: "-1.6px", fontWeight: "400" }],
        "display-lg":  ["52px", { lineHeight: "1.0",  letterSpacing: "-1.3px", fontWeight: "400" }],
        "display-md":  ["44px", { lineHeight: "1.09", letterSpacing: "-1px",   fontWeight: "400" }],
        "heading-lg":  ["32px", { lineHeight: "1.13", letterSpacing: "-0.4px", fontWeight: "400" }],
        "heading-md":  ["18px", { lineHeight: "1.33", letterSpacing: "0",      fontWeight: "600" }],
        "heading-sm":  ["18px", { lineHeight: "1.4",  letterSpacing: "0",       fontWeight: "300" }],
        "body-lg":     ["16px", { lineHeight: "1.4",  letterSpacing: "0",       fontWeight: "300" }],
        "body-md":     ["15px", { lineHeight: "1.6",  letterSpacing: "0",       fontWeight: "300" }],
        "body-tabular":["14px", { lineHeight: "1.4",  letterSpacing: "-0.42px", fontWeight: "300" }],
        "btn-md":      ["16px", { lineHeight: "1.0",  letterSpacing: "0",       fontWeight: "400" }],
        "btn-sm":      ["14px", { lineHeight: "1.0",  letterSpacing: "0",       fontWeight: "400" }],
        "caption":     ["13px", { lineHeight: "1.4",  letterSpacing: "-0.39px", fontWeight: "400" }],
        "micro":       ["11px", { lineHeight: "1.4",  letterSpacing: "0",       fontWeight: "300" }],
        "micro-cap":   ["10px", { lineHeight: "1.15", letterSpacing: "0.1px",   fontWeight: "400" }],
      },

      borderRadius: {
        card:  "24px",  /* feature cards — Coinbase rounded.xl */
        "xl":  "16px",  /* dashboard mockup chrome */
        "lg":  "12px",
        "md":  "8px",
        "sm":  "6px",
        "xs":  "4px",
        pill:  "9999px", /* all buttons, tags */
      },

      spacing: {
        xxs:  "2px",
        xs:   "4px",
        sm:   "8px",
        md:   "12px",
        lg:   "16px",
        xl:   "24px",
        xxl:  "32px",
        huge: "64px",
      },

      boxShadow: {
        sm:   "var(--shadow-sm)",
        md:   "var(--shadow-md)",
        lg:   "var(--shadow-lg)",
        glow: "var(--shadow-glow)",
      },

      animation: {
        "background-gradient":
          "background-gradient var(--background-gradient-speed, 15s) cubic-bezier(0.445, 0.05, 0.55, 0.95) infinite",
        aurora: "aurora 60s linear infinite",
      },
      keyframes: {
        aurora: {
          from: { backgroundPosition: "50% 50%, 50% 50%" },
          to:   { backgroundPosition: "350% 50%, 350% 50%" },
        },
        "background-gradient": {
          "0%, 100%": { transform: "translate(0, 0)" },
          "20%": { transform: "translate(calc(100% * var(--tx-1, 1)), calc(100% * var(--ty-1, 1)))" },
          "40%": { transform: "translate(calc(100% * var(--tx-2, -1)), calc(100% * var(--ty-2, 1)))" },
          "60%": { transform: "translate(calc(100% * var(--tx-3, 1)), calc(100% * var(--ty-3, -1)))" },
          "80%": { transform: "translate(calc(100% * var(--tx-4, -1)), calc(100% * var(--ty-4, -1)))" },
        },
      },
    },
  },
  plugins: [
    require("@tailwindcss/typography"),
    // strategy: "class" — opt-in via `.form-input`/`.form-select`/etc. rather
    // than the default global reset, since every input in this app already
    // has hand-styled classes (Input component, SearchBox, ...) that a
    // blanket base-style reset would visually clash with.
    require("@tailwindcss/forms")({ strategy: "class" }),
    require("@tailwindcss/container-queries"),
  ],
};
export default config;
