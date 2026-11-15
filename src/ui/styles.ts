import type { CSSProperties } from "react";

export const COLORS = {
  // SteamOS OLED Limited Edition matte graphite & warm machined surfaces
  bgDeep: "#16171a",
  bgCard: "#1d1f23",
  bgElevated: "#24272c",
  bgInput: "#121316",
  bgGlass: "rgba(26, 28, 32, 0.98)",
  borderSubtle: "#2e3238",
  borderStrong: "#40454e",

  // Primary accent: Deck OLED signal orange
  accent: "#ff5a26",
  accentBright: "#ff7447",
  accentInk: "#111214",
  accentSoft: "rgba(255, 90, 38, 0.14)",
  accentBorder: "#9e3b1c",

  // Brushed steel (handheld / standby / neutral hardware tags)
  steel: "#c8ccd4",
  steelSoft: "#272a30",
  steelBorder: "#3a3f48",

  // Muted industrial LED telemetry tones
  sage: "#7ec488",
  sageSoft: "#1a281e",
  sageBorder: "#31593b",
  ochre: "#e5a93c",
  ochreSoft: "#2a2214",
  ochreBorder: "#75551e",
  crimson: "#e04f44",
  crimsonSoft: "#2a1818",
  crimsonBorder: "#752d29",

  // Typography hierarchy
  textPrimary: "#eceae4",
  textSecondary: "#9ca0a8",
  textMuted: "#6c7078",
  monoFont: 'ui-monospace, "SFMono-Regular", Menlo, Monaco, Consolas, monospace',
} as const;

export const qamStyles = {
  root: {
    width: "100%",
    maxWidth: "100%",
    boxSizing: "border-box",
    overflowX: "hidden",
    color: COLORS.textPrimary,
    fontFamily: '"Motiva Sans", "Inter", system-ui, -apple-system, sans-serif',
    fontSize: "12px",
    lineHeight: 1.4,
    paddingBottom: "24px",
  } satisfies CSSProperties,

  heroCard: (isDocked = false): CSSProperties => ({
    width: "100%",
    boxSizing: "border-box",
    background: COLORS.bgCard,
    border: `1px solid ${COLORS.borderSubtle}`,
    borderTop: `2px solid ${isDocked ? COLORS.accent : COLORS.steelBorder}`,
    borderRadius: "4px",
    padding: "10px 11px",
    marginBottom: "8px",
    boxShadow: "0 2px 8px rgba(0, 0, 0, 0.45)",
  }),

  heroHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: "6px",
    marginBottom: "8px",
    minWidth: 0,
  } satisfies CSSProperties,

  brandGroup: {
    display: "flex",
    alignItems: "center",
    gap: "6px",
    minWidth: 0,
  } satisfies CSSProperties,

  brandTitle: {
    fontSize: "11.5px",
    fontWeight: 700,
    letterSpacing: "0.08em",
    textTransform: "uppercase",
    color: COLORS.textPrimary,
    whiteSpace: "nowrap",
  } satisfies CSSProperties,

  pillRow: {
    display: "flex",
    alignItems: "center",
    gap: "4px",
    flexWrap: "wrap",
    justifyContent: "flex-end",
  } satisfies CSSProperties,

  pill: (
    tone: "orangeSolid" | "orange" | "steel" | "sage" | "ochre" | "crimson",
  ): CSSProperties => {
    const palette = {
      orangeSolid: { bg: COLORS.accent, fg: COLORS.accentInk, border: COLORS.accent },
      orange: { bg: COLORS.accentSoft, fg: COLORS.accentBright, border: COLORS.accentBorder },
      steel: { bg: COLORS.steelSoft, fg: COLORS.steel, border: COLORS.steelBorder },
      sage: { bg: COLORS.sageSoft, fg: COLORS.sage, border: COLORS.sageBorder },
      ochre: { bg: COLORS.ochreSoft, fg: COLORS.ochre, border: COLORS.ochreBorder },
      crimson: { bg: COLORS.crimsonSoft, fg: COLORS.crimson, border: COLORS.crimsonBorder },
    }[tone];
    return {
      display: "inline-flex",
      alignItems: "center",
      gap: "4px",
      padding: "2px 6px",
      borderRadius: "3px",
      background: palette.bg,
      color: palette.fg,
      border: `1px solid ${palette.border}`,
      fontFamily: COLORS.monoFont,
      fontSize: "9.5px",
      fontWeight: 700,
      letterSpacing: "0.05em",
      textTransform: "uppercase",
      whiteSpace: "nowrap",
      maxWidth: "100%",
      boxSizing: "border-box",
    };
  },

  statList: {
    display: "flex",
    flexDirection: "column",
    gap: 0,
    background: "#15171b",
    border: "1px solid #292d34",
    borderRadius: "4px",
    overflow: "hidden",
    minWidth: 0,
  } satisfies CSSProperties,

  statRow: {
    display: "flex",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: "8px",
    padding: "6px 8px",
    borderRadius: 0,
    background: "transparent",
    borderBottom: "1px solid #22252b",
    minWidth: 0,
  } satisfies CSSProperties,

  statLabel: {
    display: "flex",
    alignItems: "center",
    gap: "5px",
    color: COLORS.textSecondary,
    fontSize: "11px",
    fontWeight: 600,
    flexShrink: 0,
    whiteSpace: "nowrap",
  } satisfies CSSProperties,

  statValueWrap: {
    display: "flex",
    flexDirection: "column",
    alignItems: "flex-end",
    textAlign: "right",
    minWidth: 0,
    flex: 1,
    gap: "2px",
  } satisfies CSSProperties,

  statValue: {
    color: COLORS.textPrimary,
    fontSize: "11.5px",
    fontWeight: 600,
    wordBreak: "break-word",
    overflowWrap: "anywhere",
    maxWidth: "100%",
  } satisfies CSSProperties,

  statSub: {
    color: COLORS.textSecondary,
    fontSize: "10px",
    fontFamily: COLORS.monoFont,
    fontVariantNumeric: "tabular-nums",
    wordBreak: "break-word",
    overflowWrap: "anywhere",
    maxWidth: "100%",
  } satisfies CSSProperties,

  warningCard: {
    width: "100%",
    boxSizing: "border-box",
    background: "#201818",
    border: "1px solid #4a2a28",
    borderLeft: `3px solid ${COLORS.crimson}`,
    borderRadius: "4px",
    padding: "9px 10px",
    marginBottom: "8px",
    color: COLORS.textPrimary,
  } satisfies CSSProperties,

  warningHeader: {
    display: "flex",
    alignItems: "center",
    gap: "6px",
    color: COLORS.crimson,
    fontSize: "11.5px",
    fontWeight: 700,
    marginBottom: "4px",
  } satisfies CSSProperties,

  warningBody: {
    fontSize: "11px",
    color: COLORS.textPrimary,
    lineHeight: 1.38,
    wordBreak: "break-word",
    overflowWrap: "anywhere",
  } satisfies CSSProperties,

  inlineFeedback: (tone: "orange" | "crimson" | "sage"): CSSProperties => {
    const map = {
      orange: {
        bg: COLORS.accentSoft,
        border: COLORS.accentBorder,
        accent: COLORS.accent,
        fg: COLORS.textPrimary,
      },
      crimson: {
        bg: COLORS.crimsonSoft,
        border: COLORS.crimsonBorder,
        accent: COLORS.crimson,
        fg: COLORS.textPrimary,
      },
      sage: {
        bg: COLORS.sageSoft,
        border: COLORS.sageBorder,
        accent: COLORS.sage,
        fg: COLORS.textPrimary,
      },
    }[tone];
    return {
      width: "100%",
      boxSizing: "border-box",
      borderRadius: "4px",
      padding: "6px 9px",
      marginTop: "4px",
      marginBottom: "4px",
      background: map.bg,
      border: `1px solid ${map.border}`,
      borderLeft: `3px solid ${map.accent}`,
      color: map.fg,
      fontSize: "11px",
      fontWeight: 600,
      wordBreak: "break-word",
      overflowWrap: "anywhere",
    };
  },

  certCard: {
    width: "100%",
    boxSizing: "border-box",
    background: "#15171b",
    border: `1px solid ${COLORS.borderSubtle}`,
    borderRadius: "4px",
    padding: "6px 9px",
    marginBottom: "2px",
    display: "flex",
    flexDirection: "column",
    gap: "3px",
  } satisfies CSSProperties,

  monoCode: {
    fontFamily: COLORS.monoFont,
    fontSize: "10px",
    color: COLORS.textSecondary,
    wordBreak: "break-all",
  } satisfies CSSProperties,

  overclockWarningCard: {
    width: "100%",
    boxSizing: "border-box",
    background: "#201c14",
    border: "1px solid #4d3d1e",
    borderLeft: `3px solid ${COLORS.ochre}`,
    borderRadius: "4px",
    padding: "9px 10px",
    marginBottom: "4px",
    color: COLORS.textPrimary,
  } satisfies CSSProperties,

  telemetryCard: {
    width: "100%",
    boxSizing: "border-box",
    background: "#15171b",
    border: `1px solid ${COLORS.borderSubtle}`,
    borderRadius: "4px",
    padding: "7px 9px",
    marginBottom: "2px",
    display: "flex",
    flexDirection: "column",
    gap: "4px",
  } satisfies CSSProperties,
};

export const toastStyles = {
  card: (isDocked: boolean, compact: boolean): CSSProperties => ({
    width: compact ? "100%" : "360px",
    maxWidth: "100%",
    boxSizing: "border-box",
    background: COLORS.bgGlass,
    border: `1px solid ${isDocked ? "#434852" : "#363b44"}`,
    borderRadius: "4px",
    padding: compact ? "6px 8px 6px 11px" : "10px 12px 10px 15px",
    boxShadow: "0 14px 32px rgba(0, 0, 0, 0.75)",
    color: COLORS.textPrimary,
    fontFamily: '"Motiva Sans", "Inter", system-ui, -apple-system, sans-serif',
    overflow: "hidden",
    position: "relative",
  }),

  accentStrip: (isDocked: boolean): CSSProperties => ({
    position: "absolute",
    top: 0,
    bottom: 0,
    left: 0,
    width: "3px",
    background: isDocked ? COLORS.accent : COLORS.steelBorder,
  }),

  topRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: "8px",
    marginBottom: "6px",
  } satisfies CSSProperties,

  titleRow: {
    display: "flex",
    alignItems: "center",
    gap: "7px",
    minWidth: 0,
  } satisfies CSSProperties,

  displayTitle: {
    fontSize: "13px",
    fontWeight: 700,
    color: COLORS.textPrimary,
    whiteSpace: "nowrap",
    overflow: "hidden",
    textOverflow: "ellipsis",
  } satisfies CSSProperties,

  chipsWrap: {
    display: "flex",
    flexWrap: "wrap",
    gap: "5px",
    alignItems: "center",
  } satisfies CSSProperties,

  chip: (tone: "orange" | "steel" | "ochre" | "crimson"): CSSProperties => {
    const map = {
      orange: { bg: COLORS.accentSoft, fg: COLORS.accentBright, border: COLORS.accentBorder },
      steel: { bg: COLORS.steelSoft, fg: COLORS.steel, border: COLORS.steelBorder },
      ochre: { bg: COLORS.ochreSoft, fg: COLORS.ochre, border: COLORS.ochreBorder },
      crimson: { bg: COLORS.crimsonSoft, fg: COLORS.crimson, border: COLORS.crimsonBorder },
    }[tone];
    return {
      display: "inline-flex",
      alignItems: "center",
      gap: "4px",
      padding: "2px 6px",
      borderRadius: "3px",
      background: map.bg,
      border: `1px solid ${map.border}`,
      color: map.fg,
      fontFamily: COLORS.monoFont,
      fontSize: "10px",
      fontWeight: 600,
      maxWidth: "100%",
      boxSizing: "border-box",
    };
  },
};
