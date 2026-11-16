import type { FC } from "react";
import { COLORS, toastStyles } from "./styles";
import type { TransitionPayload } from "./types";

export const SwitchJoyConIcon: FC<{ size?: number }> = ({ size = 18 }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    aria-hidden="true"
    style={{ flexShrink: 0 }}
  >
    <path
      d="M6.5 4H10.5V20H4.5C3.4 20 2.5 19.1 2.5 18V8L6.5 4Z"
      fill="#cfd6df"
    />
    <rect x="5.3" y="8.2" width="2.6" height="2.6" rx="0.6" fill="#171c24" />
    <path
      d="M13.5 4H17.5L21.5 8V18C21.5 19.1 20.6 20 19.5 20H13.5V4Z"
      fill={COLORS.accent}
    />
    <rect x="16.1" y="13.2" width="2.6" height="2.6" rx="0.6" fill="#171c24" />
  </svg>
);

export interface SwitchToastCardProps {
  transition: TransitionPayload;
  compact?: boolean;
}

export const SwitchToastCard: FC<SwitchToastCardProps> = ({ transition, compact = false }) => {
  const isDocked = transition.kind === "docked";
  const isOc = Boolean(transition.overclock_active);
  const chargeTag =
    transition.charge_limit > 0 ? `${transition.charge_limit}% Cap` : "100% Cap";
  const powerLabel =
    transition.tdp_watts != null
      ? `${transition.tdp_watts}W${isOc ? " OC" : ""} · ${chargeTag}`
      : chargeTag;

  const title = transition.display_name || (isDocked ? "External Display" : "Handheld");
  const modeWithVrr = transition.output_mode
    ? `${transition.output_mode}${transition.vrr_enabled ? " VRR" : ""}`
    : "";

  const detailParts: string[] = [];
  if (modeWithVrr) detailParts.push(modeWithVrr);
  if (transition.p1_controller) detailParts.push(`P1 ${transition.p1_controller}`);
  detailParts.push(powerLabel);
  if (transition.audio_sink) detailParts.push(transition.audio_sink);

  if (compact) {
    const compactTop = [title, modeWithVrr].filter(Boolean).join(" · ");
    const compactSub = [
      transition.p1_controller ? `P1 ${transition.p1_controller}` : "",
      powerLabel,
      transition.audio_sink || "",
    ]
      .filter(Boolean)
      .join(" · ");
    return (
      <div style={toastStyles.card(true)}>
        <div style={toastStyles.displayTitle}>{compactTop}</div>
        <div style={toastStyles.subtitle}>{compactSub}</div>
      </div>
    );
  }

  const stateLabel = isDocked ? (isOc ? "Docked · OC" : "Docked") : "Handheld";

  return (
    <div style={toastStyles.card(false)}>
      <div style={toastStyles.topRow}>
        <div style={{ display: "flex", alignItems: "center", gap: "8px", minWidth: 0 }}>
          <SwitchJoyConIcon size={17} />
          <span style={toastStyles.displayTitle}>{title}</span>
        </div>
        <span style={toastStyles.stateTag(isDocked, isOc)}>{stateLabel}</span>
      </div>
      <div style={toastStyles.subtitle}>{detailParts.join(" · ")}</div>
    </div>
  );
};
