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
        emerald: c("--color-up"),                    /* alias for gain green */
      },

      fontFamily: {
        sans:    ["var(--font-sans)", "system-ui", "sans-serif"],
        display: ["var(--font-sans)", "system-ui", "sans-serif"], /* Inter replaces Space Grotesk */
        mono:    ["var(--font-mono)", "ui-monospace", "monospace"],
      },

      fontSize: {
        /* Display tier — weight 300, negative tracking baked into Tailwind */
        "display-xxl": ["56px", { lineHeight: "1.03", letterSpacing: "-1.4px", fontWeight: "300" }],
        "display-xl":  ["48px", { lineHeight: "1.15", letterSpacing: "-0.96px", fontWeight: "300" }],
        "display-lg":  ["32px", { lineHeight: "1.1",  letterSpacing: "-0.64px", fontWeight: "300" }],
        "display-md":  ["26px", { lineHeight: "1.12", letterSpacing: "-0.26px", fontWeight: "300" }],
        "heading-lg":  ["22px", { lineHeight: "1.1",  letterSpacing: "-0.22px", fontWeight: "300" }],
        "heading-md":  ["20px", { lineHeight: "1.4",  letterSpacing: "-0.2px",  fontWeight: "300" }],
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
        card:  "12px",  /* feature cards */
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
        sm:   "0 1px 3px rgba(0,55,112,0.08), 0 1px 2px rgba(0,55,112,0.04)",
        md:   "0 8px 24px rgba(0,55,112,0.08), 0 2px 6px rgba(0,55,112,0.04)",
        lg:   "0 20px 48px rgba(0,55,112,0.10), 0 6px 16px rgba(0,55,112,0.06)",
        glow: "0 0 0 3px rgba(21,128,61,0.14), 0 4px 16px rgba(21,128,61,0.10)",
      },

      animation: {
        "background-gradient":
          "background-gradient var(--background-gradient-speed, 15s) cubic-bezier(0.445, 0.05, 0.55, 0.95) infinite",
      },
      keyframes: {
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
  plugins: [],
};
export default config;
