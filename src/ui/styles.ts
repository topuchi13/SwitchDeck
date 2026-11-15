import type { CSSProperties } from "react";

export const COLORS = {
  bgDeep: "#0e141b",
  bgCard: "#151d27",
  bgElevated: "#1a232e",
  bgGlass: "rgba(14, 20, 27, 0.94)",
  borderSubtle: "rgba(255, 255, 255, 0.08)",
  borderStrong: "rgba(255, 255, 255, 0.16)",
  neonBlue: "#00C3E3",
  neonBlueSoft: "rgba(0, 195, 227, 0.16)",
  neonBlueBorder: "rgba(0, 195, 227, 0.44)",
  neonCoral: "#FF4554",
  neonCoralSoft: "rgba(255, 69, 84, 0.16)",
  neonCoralBorder: "rgba(255, 69, 84, 0.46)",
  emerald: "#34d399",
  emeraldSoft: "rgba(52, 211, 153, 0.15)",
  emeraldBorder: "rgba(52, 211, 153, 0.42)",
  amber: "#fbbf24",
  amberSoft: "rgba(251, 191, 36, 0.14)",
  amberBorder: "rgba(251, 191, 36, 0.4)",
  textPrimary: "#f1f5f9",
  textSecondary: "#94a3b8",
  textMuted: "#64748b",
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

  heroCard: {
    width: "100%",
    boxSizing: "border-box",
    background: `linear-gradient(155deg, ${COLORS.bgElevated} 0%, ${COLORS.bgDeep} 100%)`,
    border: `1px solid ${COLORS.borderSubtle}`,
    borderRadius: "10px",
    padding: "10px 11px",
    marginBottom: "8px",
    boxShadow: "0 4px 16px rgba(0, 0, 0, 0.32)",
  } satisfies CSSProperties,

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
    fontSize: "12px",
    fontWeight: 700,
    letterSpacing: "0.06em",
    textTransform: "uppercase",
    color: COLORS.textPrimary,
    whiteSpace: "nowrap",
  } satisfies CSSProperties,

  pillRow: {
    display: "flex",
    alignItems: "center",
    gap: "5px",
    flexWrap: "wrap",
    justifyContent: "flex-end",
  } satisfies CSSProperties,

  pill: (tone: "blue" | "coral" | "emerald" | "amber" | "slate"): CSSProperties => {
    const palette = {
      blue: { bg: COLORS.neonBlueSoft, fg: COLORS.neonBlue, border: COLORS.neonBlueBorder },
      coral: { bg: COLORS.neonCoralSoft, fg: COLORS.neonCoral, border: COLORS.neonCoralBorder },
      emerald: { bg: COLORS.emeraldSoft, fg: COLORS.emerald, border: COLORS.emeraldBorder },
      amber: { bg: COLORS.amberSoft, fg: COLORS.amber, border: COLORS.amberBorder },
      slate: {
        bg: "rgba(148, 163, 184, 0.14)",
        fg: COLORS.textSecondary,
        border: "rgba(148, 163, 184, 0.28)",
      },
    }[tone];
    return {
      display: "inline-flex",
      alignItems: "center",
      gap: "4px",
      padding: "2px 7px",
      borderRadius: "999px",
      background: palette.bg,
      color: palette.fg,
      border: `1px solid ${palette.border}`,
      fontSize: "10px",
      fontWeight: 700,
      letterSpacing: "0.04em",
      textTransform: "uppercase",
      whiteSpace: "nowrap",
      maxWidth: "100%",
      boxSizing: "border-box",
    };
  },

  statList: {
    display: "flex",
    flexDirection: "column",
    gap: "6px",
    minWidth: 0,
  } satisfies CSSProperties,

  statRow: {
    display: "flex",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: "8px",
    padding: "5px 7px",
    borderRadius: "7px",
    background: "rgba(255, 255, 255, 0.03)",
    border: "1px solid rgba(255, 255, 255, 0.045)",
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
    wordBreak: "break-word",
    overflowWrap: "anywhere",
    maxWidth: "100%",
  } satisfies CSSProperties,

  warningCard: {
    width: "100%",
    boxSizing: "border-box",
    background: "linear-gradient(145deg, rgba(255, 69, 84, 0.14), rgba(251, 191, 36, 0.08))",
    border: `1px solid ${COLORS.neonCoralBorder}`,
    borderRadius: "9px",
    padding: "9px 10px",
    marginBottom: "8px",
    color: COLORS.textPrimary,
  } satisfies CSSProperties,

  warningHeader: {
    display: "flex",
    alignItems: "center",
    gap: "6px",
    color: COLORS.neonCoral,
    fontSize: "11.5px",
    fontWeight: 700,
    marginBottom: "4px",
  } satisfies CSSProperties,

  warningBody: {
    fontSize: "11px",
    color: "#e2e8f0",
    lineHeight: 1.38,
    wordBreak: "break-word",
    overflowWrap: "anywhere",
  } satisfies CSSProperties,

  inlineFeedback: (tone: "blue" | "coral" | "emerald"): CSSProperties => {
    const map = {
      blue: { bg: COLORS.neonBlueSoft, border: COLORS.neonBlueBorder, fg: COLORS.neonBlue },
      coral: { bg: COLORS.neonCoralSoft, border: COLORS.neonCoralBorder, fg: COLORS.neonCoral },
      emerald: { bg: COLORS.emeraldSoft, border: COLORS.emeraldBorder, fg: COLORS.emerald },
    }[tone];
    return {
      width: "100%",
      boxSizing: "border-box",
      borderRadius: "7px",
      padding: "6px 9px",
      marginTop: "4px",
      marginBottom: "4px",
      background: map.bg,
      border: `1px solid ${map.border}`,
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
    background: "rgba(255, 255, 255, 0.03)",
    border: `1px solid ${COLORS.borderSubtle}`,
    borderRadius: "8px",
    padding: "6px 9px",
    marginBottom: "2px",
    display: "flex",
    flexDirection: "column",
    gap: "3px",
  } satisfies CSSProperties,

  monoCode: {
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
    fontSize: "10px",
    color: COLORS.textSecondary,
    wordBreak: "break-all",
  } satisfies CSSProperties,
};

export const toastStyles = {
  card: (isDocked: boolean, compact: boolean): CSSProperties => ({
    width: compact ? "100%" : "360px",
    maxWidth: "100%",
    boxSizing: "border-box",
    background: COLORS.bgGlass,
    backdropFilter: "blur(14px)",
    WebkitBackdropFilter: "blur(14px)",
    border: `1px solid ${isDocked ? COLORS.neonBlueBorder : COLORS.neonCoralBorder}`,
    borderRadius: "12px",
    padding: compact ? "6px 8px" : "11px 13px",
    boxShadow: isDocked
      ? "0 12px 32px rgba(0, 0, 0, 0.55), 0 0 22px rgba(0, 195, 227, 0.22)"
      : "0 12px 32px rgba(0, 0, 0, 0.55), 0 0 22px rgba(255, 69, 84, 0.22)",
    color: COLORS.textPrimary,
    fontFamily: '"Motiva Sans", "Inter", system-ui, -apple-system, sans-serif',
    overflow: "hidden",
    position: "relative",
  }),

  accentStrip: (isDocked: boolean): CSSProperties => ({
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    height: "3px",
    background: isDocked
      ? `linear-gradient(90deg, ${COLORS.neonBlue} 0%, #38bdf8 65%, ${COLORS.neonCoral} 100%)`
      : `linear-gradient(90deg, ${COLORS.neonCoral} 0%, #fb7185 65%, ${COLORS.neonBlue} 100%)`,
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

  chip: (tone: "blue" | "coral" | "slate"): CSSProperties => {
    const map = {
      blue: { bg: COLORS.neonBlueSoft, fg: COLORS.neonBlue, border: COLORS.neonBlueBorder },
      coral: { bg: COLORS.neonCoralSoft, fg: COLORS.neonCoral, border: COLORS.neonCoralBorder },
      slate: {
        bg: "rgba(255, 255, 255, 0.06)",
        fg: "#e2e8f0",
        border: "rgba(255, 255, 255, 0.11)",
      },
    }[tone];
    return {
      display: "inline-flex",
      alignItems: "center",
      gap: "4px",
      padding: "2px 7px",
      borderRadius: "6px",
      background: map.bg,
      border: `1px solid ${map.border}`,
      color: map.fg,
      fontSize: "10.5px",
      fontWeight: 600,
      maxWidth: "100%",
      boxSizing: "border-box",
    };
  },
};
