import type { FC } from "react";
import { FaBolt, FaGamepad, FaSlidersH, FaTv, FaVolumeUp } from "react-icons/fa";
import { COLORS, qamStyles, toastStyles } from "./styles";
import type { TransitionPayload } from "./types";

export const SwitchJoyConIcon: FC<{ size?: number }> = ({ size = 20 }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    aria-hidden="true"
    style={{ flexShrink: 0 }}
  >
    {/* Left brushed-steel grip module */}
    <path
      d="M6.2 4H10.5V20H4.5C3.4 20 2.5 19.1 2.5 18V7.7L6.2 4Z"
      fill="#d8d5ce"
    />
    <rect x="5.2" y="8" width="2.8" height="2.8" rx="0.6" fill="#16171a" />
    {/* Right Deck OLED signal-orange dock module */}
    <path
      d="M13.5 4H17.8L21.5 7.7V18C21.5 19.1 20.6 20 19.5 20H13.5V4Z"
      fill={COLORS.accent}
    />
    <rect x="16" y="13.2" width="2.8" height="2.8" rx="0.6" fill="#16171a" />
  </svg>
);

export interface SwitchToastCardProps {
  transition: TransitionPayload;
  compact?: boolean;
}

export const SwitchToastCard: FC<SwitchToastCardProps> = ({ transition, compact = false }) => {
  const isDocked = transition.kind === "docked";
  const isOc = Boolean(transition.overclock_active);
  const powerLabel =
    transition.tdp_watts != null
      ? `${transition.tdp_watts}W ${isOc ? "OC" : ""}· ${
          transition.charge_limit > 0 ? `${transition.charge_limit}% Cap` : "100% Cap"
        }`.replace("  ", " ")
      : transition.charge_limit > 0
        ? `${transition.charge_limit}% Cap`
        : "Uncapped";

  return (
    <div style={toastStyles.card(isDocked, compact)}>
      <div style={toastStyles.accentStrip(isDocked)} />
      <div style={toastStyles.topRow}>
        <div style={toastStyles.titleRow}>
          <SwitchJoyConIcon size={compact ? 18 : 20} />
          <span style={toastStyles.displayTitle}>
            {transition.display_name || (isDocked ? "External Display" : "Handheld")}
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "4px", flexShrink: 0 }}>
          {isOc && <span style={qamStyles.pill("ochre")}>OC</span>}
          {transition.vrr_enabled && <span style={qamStyles.pill("orange")}>VRR</span>}
          <span style={qamStyles.pill(isDocked ? "orangeSolid" : "steel")}>
            {isDocked ? "Docked" : "Handheld"}
          </span>
        </div>
      </div>

      <div style={toastStyles.chipsWrap}>
        {transition.output_mode && (
          <span style={toastStyles.chip(isDocked ? "orange" : "steel")}>
            <FaTv size={10} />
            <span>{transition.output_mode}</span>
          </span>
        )}
        <span style={toastStyles.chip("steel")}>
          <FaGamepad size={10} />
          <span>P1: {transition.p1_controller}</span>
        </span>
        {transition.scaling_summary && (
          <span style={toastStyles.chip("steel")}>
            <FaSlidersH size={10} />
            <span>{transition.scaling_summary}</span>
          </span>
        )}
        <span style={toastStyles.chip(isOc ? "ochre" : isDocked ? "orange" : "steel")}>
          <FaBolt size={10} />
          <span>{powerLabel}</span>
        </span>
        {transition.audio_sink && (
          <span style={toastStyles.chip("steel")}>
            <FaVolumeUp size={10} />
            <span>{transition.audio_sink}</span>
          </span>
        )}
      </div>
    </div>
  );
};
