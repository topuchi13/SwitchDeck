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
    <path
      d="M5.5 4.2C3.84 4.2 2.5 5.54 2.5 7.2V16.8C2.5 18.46 3.84 19.8 5.5 19.8H10.3V4.2H5.5Z"
      fill={COLORS.neonBlue}
      fillOpacity={0.92}
    />
    <circle cx="6.4" cy="9.2" r="1.45" fill="#0b1118" />
    <path
      d="M13.7 4.2V19.8H18.5C20.16 19.8 21.5 18.46 21.5 16.8V7.2C21.5 5.54 20.16 4.2 18.5 4.2H13.7Z"
      fill={COLORS.neonCoral}
      fillOpacity={0.92}
    />
    <circle cx="17.6" cy="14.2" r="1.45" fill="#0b1118" />
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
      <div style={{ ...toastStyles.topRow, marginTop: "2px" }}>
        <div style={toastStyles.titleRow}>
          <SwitchJoyConIcon size={compact ? 18 : 20} />
          <span style={toastStyles.displayTitle}>
            {transition.display_name || (isDocked ? "External Display" : "Handheld")}
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "4px", flexShrink: 0 }}>
          {isOc && <span style={qamStyles.pill("amber")}>OC</span>}
          {transition.vrr_enabled && <span style={qamStyles.pill("blue")}>VRR</span>}
          <span style={qamStyles.pill(isDocked ? "blue" : "coral")}>
            {isDocked ? "Docked" : "Handheld"}
          </span>
        </div>
      </div>

      <div style={toastStyles.chipsWrap}>
        {transition.output_mode && (
          <span style={toastStyles.chip(isDocked ? "blue" : "slate")}>
            <FaTv size={10} />
            <span>{transition.output_mode}</span>
          </span>
        )}
        <span style={toastStyles.chip("slate")}>
          <FaGamepad size={10} />
          <span>P1: {transition.p1_controller}</span>
        </span>
        {transition.scaling_summary && (
          <span style={toastStyles.chip("slate")}>
            <FaSlidersH size={10} />
            <span>{transition.scaling_summary}</span>
          </span>
        )}
        <span style={toastStyles.chip(isOc ? "amber" : isDocked ? "blue" : "coral")}>
          <FaBolt size={10} />
          <span>{powerLabel}</span>
        </span>
        {transition.audio_sink && (
          <span style={toastStyles.chip("slate")}>
            <FaVolumeUp size={10} />
            <span>{transition.audio_sink}</span>
          </span>
        )}
      </div>
    </div>
  );
};
