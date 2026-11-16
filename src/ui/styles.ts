import type { CSSProperties } from "react";

export const COLORS = {
  // Calm native SteamOS / GamepadUI slate palette
  bgDeep: "#0e141b",
  bgCard: "#1b2028",
  bgElevated: "#252b36",
  bgInput: "#12161d",
  bgGlass: "rgba(23, 28, 36, 0.96)",
  borderSubtle: "rgba(255, 255, 255, 0.08)",
  borderStrong: "rgba(255, 255, 255, 0.16)",

  // SteamOS native blue accent
  accent: "#1a9fff",
  accentBright: "#66c0f4",
  accentInk: "#ffffff",
  accentSoft: "rgba(26, 159, 255, 0.14)",
  accentBorder: "rgba(26, 159, 255, 0.35)",

  // Muted semantic tones (text/subtle accents only)
  steel: "#b8c2ce",
  steelSoft: "rgba(255, 255, 255, 0.06)",
  steelBorder: "rgba(255, 255, 255, 0.12)",
  sage: "#7bc48b",
  sageSoft: "rgba(123, 196, 139, 0.12)",
  sageBorder: "rgba(123, 196, 139, 0.32)",
  ochre: "#e2ad52",
  ochreSoft: "rgba(226, 173, 82, 0.12)",
  ochreBorder: "rgba(226, 173, 82, 0.32)",
  crimson: "#e06c6c",
  crimsonSoft: "rgba(224, 108, 108, 0.12)",
  crimsonBorder: "rgba(224, 108, 108, 0.32)",

  // Typography
  textPrimary: "#e6ebf0",
  textSecondary: "#95a0ad",
  textMuted: "#687280",
  uiFont: '"Motiva Sans", system-ui, -apple-system, BlinkMacSystemFont, sans-serif',
  monoFont: 'ui-monospace, "SFMono-Regular", Menlo, Monaco, Consolas, monospace',
} as const;

export const qamStyles = {
  root: {
    width: "100%",
    maxWidth: "100%",
    boxSizing: "border-box",
    overflowX: "hidden",
    color: COLORS.textPrimary,
    fontFamily: COLORS.uiFont,
    fontSize: "13px",
    lineHeight: 1.4,
    paddingBottom: "24px",
  } satisfies CSSProperties,

  statusSummaryRow: {
    display: "flex",
    alignItems: "baseline",
    justifyContent: "space-between",
    gap: "12px",
    padding: "4px 2px",
    minWidth: 0,
  } satisfies CSSProperties,

  statusKey: {
    color: COLORS.textSecondary,
    fontSize: "12px",
    flexShrink: 0,
    whiteSpace: "nowrap",
  } satisfies CSSProperties,

  statusVal: {
    color: COLORS.textPrimary,
    fontSize: "12px",
    fontWeight: 500,
    textAlign: "right",
    minWidth: 0,
    wordBreak: "break-word",
    overflowWrap: "anywhere",
  } satisfies CSSProperties,

  helperNote: (tone: "neutral" | "accent" | "sage" | "ochre" | "crimson" = "neutral"): CSSProperties => {
    const colorMap = {
      neutral: COLORS.textSecondary,
      accent: COLORS.accentBright,
      sage: COLORS.sage,
      ochre: COLORS.ochre,
      crimson: COLORS.crimson,
    };
    return {
      width: "100%",
      boxSizing: "border-box",
      fontSize: "11.5px",
      lineHeight: 1.4,
      color: colorMap[tone],
      padding: "4px 2px",
      wordBreak: "break-word",
      overflowWrap: "anywhere",
    };
  },

  monoSubtle: {
    fontFamily: COLORS.monoFont,
    fontSize: "10.5px",
    color: COLORS.textMuted,
    wordBreak: "break-all",
  } satisfies CSSProperties,
};

export const toastStyles = {
  card: (compact: boolean): CSSProperties => ({
    width: compact ? "100%" : "340px",
    maxWidth: "100%",
    boxSizing: "border-box",
    background: compact ? "transparent" : COLORS.bgGlass,
    border: compact ? "none" : `1px solid ${COLORS.borderSubtle}`,
    borderRadius: compact ? 0 : "8px",
    padding: compact ? 0 : "10px 14px",
    boxShadow: compact ? "none" : "0 10px 28px rgba(0, 0, 0, 0.55)",
    color: COLORS.textPrimary,
    fontFamily: COLORS.uiFont,
  }),

  topRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: "10px",
    marginBottom: "3px",
  } satisfies CSSProperties,

  displayTitle: {
    fontSize: "13px",
    fontWeight: 600,
    color: COLORS.textPrimary,
    whiteSpace: "nowrap",
    overflow: "hidden",
    textOverflow: "ellipsis",
  } satisfies CSSProperties,

  stateTag: (isDocked: boolean, isOc: boolean): CSSProperties => ({
    fontSize: "11.5px",
    fontWeight: 600,
    color: isOc ? COLORS.ochre : isDocked ? COLORS.accentBright : COLORS.textSecondary,
    whiteSpace: "nowrap",
    flexShrink: 0,
  }),

  subtitle: {
    fontSize: "11.5px",
    color: COLORS.textSecondary,
    lineHeight: 1.35,
    wordBreak: "break-word",
    overflowWrap: "anywhere",
  } satisfies CSSProperties,
};
