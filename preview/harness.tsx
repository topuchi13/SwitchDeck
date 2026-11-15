import { useMemo, useState } from "react";
import type { FC } from "react";
import { createRoot } from "react-dom/client";
import { FaBatteryThreeQuarters, FaChevronLeft, FaEllipsisH, FaWifi } from "react-icons/fa";
import { QuickAccessPanel } from "../src/ui/QuickAccessPanel";
import { COLORS } from "../src/ui/styles";
import { SwitchJoyConIcon, SwitchToastCard } from "../src/ui/SwitchToast";
import type {
  DaemonStatus,
  DockProfile,
  SwitchDeckTransport,
  TransitionPayload,
} from "../src/ui/types";

type ScenarioKey = "handheld" | "docked_s90c" | "docked_warning" | "tv_pairing";

interface ScenarioData {
  key: ScenarioKey;
  label: string;
  resolutionLabel: string;
  status: DaemonStatus;
  profile: DockProfile;
  toast: TransitionPayload | null;
  scrollSection: "top" | "scaling" | "tv";
}

const SCENARIOS: Record<ScenarioKey, ScenarioData> = {
  handheld: {
    key: "handheld",
    label: "Handheld (LCD)",
    resolutionLabel: "1280x800",
    scrollSection: "top",
    toast: null,
    status: {
      deck_model: "Jupiter",
      is_docked: false,
      ac_online: false,
      active_connector: null,
      active_edid_id: null,
      selected_output_mode: null,
      builtin_controller_bound: true,
      active_controllers: [],
      sleeping_controllers: [],
      unhandled_dongles: [],
      lcd_bluetooth_wakeup_enabled: false,
      charge_limit: -1,
      tdp_watts: 11,
      last_scaling: {
        target_width: 1280,
        target_height: 800,
        scaling_filter: "LINEAR",
        scaling_scaler: "FIT",
        fsr_sharpness: 2,
        enable_vrr: false,
        reason: "Handheld native 1280x800",
      },
      audio_sink: "Deck Built-in Speakers",
      manual_keep_builtin: false,
      travel_charge_override: false,
      transition_seq: 1,
      last_transition: null,
      last_error: null,
    },
    profile: {
      profile_id: "default",
      display_name: "Default Dock",
      preferred_container_width: 1920,
      preferred_container_height: 1080,
      fsr_sharpness: 2,
      docked_tdp_watts: 15,
      handheld_tdp_watts: 11,
      docked_charge_limit: 80,
      docked_volume: 0.65,
      handheld_volume: 0.5,
      auto_pause_on_undock: true,
      adaptive_gpu_downscale: true,
      tv: {
        driver: "cec",
        host: "",
        port: 8002,
        mac_address: "",
        hdmi_input: "HDMI2",
        webhook_url: "",
        auto_power_on: true,
        auto_switch_input: true,
      },
    },
  },

  docked_s90c: {
    key: "docked_s90c",
    label: "Docked S90C + Toast",
    resolutionLabel: "1920x1080",
    scrollSection: "top",
    toast: {
      seq: 2,
      kind: "docked",
      display_name: "SAMSUNG S90C",
      output_mode: "2560x1440@120Hz",
      vrr_enabled: true,
      p1_controller: "Xbox Wireless Controller",
      scaling_summary: "1920x1080 FSR",
      tdp_watts: 15,
      charge_limit: 80,
      audio_sink: "HDMI · SAMSUNG S90C",
    },
    status: {
      deck_model: "Jupiter",
      is_docked: true,
      ac_online: true,
      active_connector: "card1-DP-1",
      active_edid_id: "SAM_SAMSUNG_S90C_8f31c0a2",
      selected_output_mode: {
        width: 2560,
        height: 1440,
        refresh_hz: 120,
        preferred: true,
      },
      builtin_controller_bound: false,
      active_controllers: [
        {
          input_name: "input14",
          name: "Xbox Wireless Controller (2.4GHz)",
          vendor_id: "045e",
          product_id: "0b12",
          transport: "dongle_24g",
          is_actively_awake: true,
          wakeup_count: 1,
        },
      ],
      sleeping_controllers: [],
      unhandled_dongles: [],
      lcd_bluetooth_wakeup_enabled: true,
      charge_limit: 80,
      tdp_watts: 15,
      last_scaling: {
        target_width: 1920,
        target_height: 1080,
        scaling_filter: "FSR",
        scaling_scaler: "FIT",
        fsr_sharpness: 2,
        enable_vrr: true,
        reason: "Upscaling 1080p game to 1440p120",
      },
      audio_sink: "HDMI · SAMSUNG S90C",
      manual_keep_builtin: false,
      travel_charge_override: false,
      transition_seq: 2,
      last_transition: null,
      last_error: null,
    },
    profile: {
      profile_id: "SAM_SAMSUNG_S90C_8f31c0a2",
      display_name: "SAMSUNG S90C",
      preferred_container_width: 1920,
      preferred_container_height: 1080,
      fsr_sharpness: 2,
      docked_tdp_watts: 15,
      handheld_tdp_watts: 11,
      docked_charge_limit: 80,
      docked_volume: 0.65,
      handheld_volume: 0.5,
      auto_pause_on_undock: true,
      adaptive_gpu_downscale: true,
      tv: {
        driver: "samsung_tizen",
        host: "192.168.1.42",
        port: 8002,
        mac_address: "B8:BC:5B:9C:11:2A",
        hdmi_input: "HDMI2",
        webhook_url: "",
        auto_power_on: true,
        auto_switch_input: true,
      },
      tv_paired: true,
      tv_cert_fingerprint:
        "8f3c9d104b77aa21e8050a1bc9e7c109d3fa44b891003c72fe91a104bcde9012",
    },
  },

  docked_warning: {
    key: "docked_warning",
    label: "045e:02fe Alert + 720p FSR",
    resolutionLabel: "1920x1080",
    scrollSection: "top",
    toast: null,
    status: {
      deck_model: "Jupiter",
      is_docked: true,
      ac_online: true,
      active_connector: "card1-HDMI-A-1",
      active_edid_id: "LGD_LG_TV_4c2019ab",
      selected_output_mode: {
        width: 1920,
        height: 1080,
        refresh_hz: 60,
        preferred: true,
      },
      builtin_controller_bound: true,
      active_controllers: [],
      sleeping_controllers: [
        {
          input_name: "input18",
          name: "8BitDo Ultimate 2.4GHz",
          vendor_id: "2dc8",
          product_id: "3106",
          transport: "dongle_24g",
          is_actively_awake: false,
          wakeup_count: 0,
        },
      ],
      unhandled_dongles: [
        {
          usb_id: "045e:02fe",
          device_name: "Xbox Wireless Adapter for Windows",
          sysfs_path: "/sys/bus/usb/devices/1-1.3",
          remediation:
            "Proprietary MT76xx dongle lacks an active xone/xow driver. Install dlundqvist/xone or pair controller over Bluetooth.",
        },
      ],
      lcd_bluetooth_wakeup_enabled: true,
      charge_limit: -1,
      tdp_watts: 15,
      last_scaling: {
        target_width: 1920,
        target_height: 1080,
        scaling_filter: "FSR",
        scaling_scaler: "FIT",
        fsr_sharpness: 3,
        enable_vrr: false,
        reason: "720p AAA game upscaled to 1080p via FSR",
      },
      audio_sink: "HDMI · Living Room TV",
      manual_keep_builtin: true,
      travel_charge_override: true,
      transition_seq: 3,
      last_transition: null,
      last_error: null,
    },
    profile: {
      profile_id: "LGD_LG_TV_4c2019ab",
      display_name: "LG OLED C3",
      preferred_container_width: 1920,
      preferred_container_height: 1080,
      fsr_sharpness: 3,
      docked_tdp_watts: 15,
      handheld_tdp_watts: 11,
      docked_charge_limit: 80,
      docked_volume: 0.6,
      handheld_volume: 0.5,
      auto_pause_on_undock: true,
      adaptive_gpu_downscale: true,
      tv: {
        driver: "cec",
        host: "",
        port: 8002,
        mac_address: "",
        hdmi_input: "HDMI1",
        webhook_url: "",
        auto_power_on: true,
        auto_switch_input: true,
      },
    },
  },

  tv_pairing: {
    key: "tv_pairing",
    label: "Scaling + Tizen Pairing",
    resolutionLabel: "1280x800",
    scrollSection: "scaling",
    toast: null,
    status: {
      deck_model: "Galileo",
      is_docked: true,
      ac_online: true,
      active_connector: "card1-DP-1",
      active_edid_id: "SAM_SAMSUNG_S90C_8f31c0a2",
      selected_output_mode: {
        width: 2560,
        height: 1440,
        refresh_hz: 120,
        preferred: true,
      },
      builtin_controller_bound: false,
      active_controllers: [
        {
          input_name: "input11",
          name: "DualSense Wireless Controller",
          vendor_id: "054c",
          product_id: "0ce6",
          transport: "bluetooth",
          is_actively_awake: true,
          wakeup_count: 2,
        },
      ],
      sleeping_controllers: [],
      unhandled_dongles: [],
      lcd_bluetooth_wakeup_enabled: false,
      charge_limit: 80,
      tdp_watts: 15,
      last_scaling: {
        target_width: 1920,
        target_height: 1080,
        scaling_filter: "FSR",
        scaling_scaler: "FIT",
        fsr_sharpness: 2,
        enable_vrr: true,
        reason: "Upscaling 1080p game to 1440p120",
      },
      audio_sink: "HDMI · SAMSUNG S90C",
      manual_keep_builtin: false,
      travel_charge_override: false,
      transition_seq: 4,
      last_transition: null,
      last_error: null,
    },
    profile: {
      profile_id: "SAM_SAMSUNG_S90C_8f31c0a2",
      display_name: "SAMSUNG S90C",
      preferred_container_width: 1920,
      preferred_container_height: 1080,
      fsr_sharpness: 2,
      docked_tdp_watts: 15,
      handheld_tdp_watts: 11,
      docked_charge_limit: 80,
      docked_volume: 0.65,
      handheld_volume: 0.5,
      auto_pause_on_undock: true,
      adaptive_gpu_downscale: true,
      tv: {
        driver: "samsung_tizen",
        host: "192.168.1.42",
        port: 8002,
        mac_address: "B8:BC:5B:9C:11:2A",
        hdmi_input: "HDMI2",
        webhook_url: "",
        auto_power_on: true,
        auto_switch_input: true,
      },
      tv_paired: true,
      tv_cert_fingerprint:
        "8f3c9d104b77aa21e8050a1bc9e7c109d3fa44b891003c72fe91a104bcde9012",
    },
  },
};

function readInitialScenario(): ScenarioKey {
  const params = new URLSearchParams(window.location.search);
  const raw = params.get("scenario") as ScenarioKey | null;
  if (raw && raw in SCENARIOS) {
    return raw;
  }
  return "docked_s90c";
}

const ZeldaBackdrop: FC<{ isDocked: boolean; activeGameRes: string }> = ({
  isDocked,
  activeGameRes,
}) => (
  <div
    style={{
      position: "absolute",
      inset: 0,
      background:
        "radial-gradient(circle at 36% 42%, #1d4e68 0%, #102a3d 42%, #09131d 85%, #050a10 100%)",
      overflow: "hidden",
    }}
  >
    {/* Simulated Hyrule Field / Moon & Clock Tower atmospheric SVG backdrop */}
    <svg
      viewBox="0 0 1280 720"
      preserveAspectRatio="xMidYMid slice"
      style={{ position: "absolute", inset: 0, width: "100%", height: "100%", opacity: 0.86 }}
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="skyGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#091628" />
          <stop offset="55%" stopColor="#173d59" />
          <stop offset="100%" stopColor="#26544e" />
        </linearGradient>
        <radialGradient id="moonGlow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#fef3c7" stopOpacity="0.95" />
          <stop offset="45%" stopColor="#fde68a" stopOpacity="0.45" />
          <stop offset="100%" stopColor="#fde68a" stopOpacity="0" />
        </radialGradient>
      </defs>
      <rect width="1280" height="720" fill="url(#skyGrad)" />
      <circle cx="430" cy="210" r="190" fill="url(#moonGlow)" />
      <circle cx="430" cy="210" r="56" fill="#fef9c3" opacity="0.9" />
      <path d="M0 470 Q240 390 520 450 T1020 420 L1280 460 L1280 720 L0 720 Z" fill="#0f282b" />
      <path d="M0 540 Q330 480 650 530 T1280 510 L1280 720 L0 720 Z" fill="#0b1f22" />
      {/* Subtle Triforce crest */}
      <g transform="translate(430, 355)" opacity="0.22">
        <polygon points="0,-54 -46,24 46,24" fill="#facc15" />
        <polygon points="-46,24 -92,102 0,102" fill="#facc15" />
        <polygon points="46,24 0,102 92,102" fill="#facc15" />
      </g>
    </svg>

    {/* Simulated Game HUD Hearts + Minimap */}
    <div
      style={{
        position: "absolute",
        top: "52px",
        left: "28px",
        display: "flex",
        flexDirection: "column",
        gap: "8px",
      }}
    >
      <div style={{ display: "flex", gap: "4px" }}>
        {Array.from({ length: 8 }).map((_, idx) => (
          <span
            key={idx}
            style={{
              width: "14px",
              height: "14px",
              borderRadius: "4px",
              background: idx < 7 ? "#ef4444" : "rgba(255,255,255,0.22)",
              boxShadow: idx < 7 ? "0 0 8px rgba(239,68,68,0.55)" : "none",
              display: "inline-block",
            }}
          />
        ))}
      </div>
      <div
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: "8px",
          padding: "5px 10px",
          borderRadius: "8px",
          background: "rgba(9, 14, 21, 0.72)",
          border: "1px solid rgba(255,255,255,0.12)",
          color: "#cbd5e1",
          fontSize: "11px",
          fontWeight: 600,
        }}
      >
        <span style={{ color: "#facc15", fontWeight: 700 }}>Zelda64Recompiled</span>
        <span>·</span>
        <span>{activeGameRes}</span>
        <span>·</span>
        <span style={{ color: isDocked ? COLORS.neonBlue : COLORS.neonCoral }}>
          {isDocked ? "16:9 Docked Container" : "16:10 Handheld"}
        </span>
      </div>
    </div>
  </div>
);

const PreviewApp: FC = () => {
  const [scenarioKey, setScenarioKey] = useState<ScenarioKey>(() => readInitialScenario());
  const baseScenario = SCENARIOS[scenarioKey];

  const [status, setStatus] = useState<DaemonStatus>(() => structuredClone(baseScenario.status));
  const [profile, setProfile] = useState<DockProfile>(() => structuredClone(baseScenario.profile));
  const [toast, setToast] = useState<TransitionPayload | null>(() =>
    baseScenario.toast ? structuredClone(baseScenario.toast) : null,
  );

  const selectScenario = (key: ScenarioKey) => {
    const next = SCENARIOS[key];
    setScenarioKey(key);
    setStatus(structuredClone(next.status));
    setProfile(structuredClone(next.profile));
    setToast(next.toast ? structuredClone(next.toast) : null);
    const url = new URL(window.location.href);
    url.searchParams.set("scenario", key);
    window.history.replaceState({}, "", url.toString());
  };

  const transport: SwitchDeckTransport = useMemo(
    () => ({
      async getStatus() {
        return status;
      },
      async getActiveProfile() {
        return profile;
      },
      async updateProfile(patch) {
        const nextProf: DockProfile = {
          ...profile,
          ...(patch as Partial<DockProfile>),
          tv: {
            ...profile.tv,
            ...((patch.tv as Partial<DockProfile["tv"]>) || {}),
          },
        };
        setProfile(nextProf);
        setStatus((prev) => ({
          ...prev,
          tdp_watts: prev.is_docked ? nextProf.docked_tdp_watts : nextProf.handheld_tdp_watts,
        }));
        return nextProf;
      },
      async setKeepBuiltin(enabled) {
        const next: DaemonStatus = {
          ...status,
          manual_keep_builtin: enabled,
          builtin_controller_bound: enabled || !status.is_docked || status.active_controllers.length === 0,
        };
        setStatus(next);
        return next;
      },
      async rebindBuiltin() {
        const next: DaemonStatus = {
          ...status,
          manual_keep_builtin: true,
          builtin_controller_bound: true,
        };
        setStatus(next);
        return next;
      },
      async setChargeOverride(enabled) {
        const next: DaemonStatus = {
          ...status,
          travel_charge_override: enabled,
          charge_limit: enabled ? -1 : status.is_docked ? profile.docked_charge_limit : -1,
        };
        setStatus(next);
        return next;
      },
      async nudgeDisplay() {
        return { ok: true };
      },
      async pairSamsungTv(host, port = 8002, mac = "") {
        const nextProf: DockProfile = {
          ...profile,
          tv: { ...profile.tv, driver: "samsung_tizen", host, port, mac_address: mac || profile.tv.mac_address },
          tv_paired: true,
          tv_cert_fingerprint:
            profile.tv_cert_fingerprint ||
            "8f3c9d104b77aa21e8050a1bc9e7c109d3fa44b891003c72fe91a104bcde9012",
        };
        setProfile(nextProf);
        return {
          ok: true,
          host,
          port,
          token_saved: true,
          cert_fingerprint: nextProf.tv_cert_fingerprint,
          profile: nextProf,
        };
      },
      async testTvWake() {
        return { ok: true };
      },
      async applyNativeAppResolution() {
        return true;
      },
    }),
    [profile, status],
  );

  const activeGameRes = status.is_docked
    ? `${profile.preferred_container_width}x${profile.preferred_container_height}`
    : "1280x800";

  return (
    <div
      style={{
        position: "relative",
        width: "100vw",
        height: "100vh",
        overflow: "hidden",
        background: "#060a0f",
        color: COLORS.textPrimary,
        fontFamily: '"Motiva Sans", "Inter", system-ui, -apple-system, sans-serif',
      }}
    >
      <ZeldaBackdrop isDocked={status.is_docked} activeGameRes={activeGameRes} />

      {/* SteamOS Top Status Bar */}
      <header
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: "360px",
          height: "36px",
          padding: "0 18px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          background: "linear-gradient(180deg, rgba(8, 12, 18, 0.85) 0%, rgba(8, 12, 18, 0) 100%)",
          fontSize: "12px",
          color: "#cbd5e1",
          zIndex: 5,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "10px", fontWeight: 600 }}>
          <span style={{ color: COLORS.textPrimary }}>SteamOS 3.7</span>
          <span style={{ color: COLORS.textMuted }}>|</span>
          <span>{baseScenario.label}</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "12px", fontWeight: 600 }}>
          <FaWifi size={12} color={COLORS.neonBlue} />
          <span style={{ display: "inline-flex", alignItems: "center", gap: "4px" }}>
            <FaBatteryThreeQuarters size={13} color={COLORS.emerald} />
            <span>{status.charge_limit > 0 ? `${status.charge_limit}% Cap` : "100%"}</span>
          </span>
          <span>13:24</span>
        </div>
      </header>

      {/* Switch Click-Clack HUD Toast Overlay */}
      {toast && (
        <div
          style={{
            position: "absolute",
            top: "52px",
            left: "calc((100vw - 360px) / 2)",
            transform: "translateX(-50%)",
            zIndex: 20,
          }}
        >
          <SwitchToastCard transition={toast} />
        </div>
      )}

      {/* Interactive Scenario Switcher on bottom-left (unobtrusive pill bar) */}
      <div
        style={{
          position: "absolute",
          bottom: "44px",
          left: "24px",
          display: "flex",
          flexWrap: "wrap",
          gap: "6px",
          zIndex: 10,
        }}
      >
        {(Object.keys(SCENARIOS) as ScenarioKey[]).map((key) => {
          const active = key === scenarioKey;
          return (
            <button
              key={key}
              type="button"
              onClick={() => selectScenario(key)}
              style={{
                padding: "5px 10px",
                borderRadius: "999px",
                border: `1px solid ${active ? COLORS.neonBlueBorder : "rgba(255,255,255,0.14)"}`,
                background: active ? "rgba(0, 195, 227, 0.22)" : "rgba(10, 15, 22, 0.78)",
                color: active ? COLORS.neonBlue : COLORS.textSecondary,
                fontSize: "11px",
                fontWeight: 600,
                cursor: "pointer",
                backdropFilter: "blur(8px)",
              }}
            >
              {SCENARIOS[key].label}
            </button>
          );
        })}
      </div>

      {/* SteamOS Bottom Controller Legend */}
      <footer
        style={{
          position: "absolute",
          bottom: 0,
          left: 0,
          right: "360px",
          height: "34px",
          padding: "0 18px",
          display: "flex",
          alignItems: "center",
          gap: "16px",
          background: "linear-gradient(0deg, rgba(8, 12, 18, 0.9) 0%, rgba(8, 12, 18, 0) 100%)",
          fontSize: "11px",
          color: COLORS.textSecondary,
          zIndex: 5,
        }}
      >
        <span>
          <strong style={{ color: COLORS.textPrimary }}>A</strong> Select
        </span>
        <span>
          <strong style={{ color: COLORS.textPrimary }}>B</strong> Back
        </span>
        <span>
          <strong style={{ color: COLORS.neonBlue }}>•••</strong> Quick Access
        </span>
      </footer>

      {/* SteamOS GamepadUI Quick Access Menu (360px right drawer, 340px inner content width) */}
      <aside
        aria-label="SteamOS Quick Access Menu"
        style={{
          position: "absolute",
          top: 0,
          right: 0,
          bottom: 0,
          width: "360px",
          boxSizing: "border-box",
          background: "linear-gradient(180deg, #121923 0%, #0d131a 100%)",
          borderLeft: "1px solid rgba(255, 255, 255, 0.1)",
          boxShadow: "-12px 0 36px rgba(0, 0, 0, 0.65)",
          display: "flex",
          flexDirection: "column",
          zIndex: 15,
        }}
      >
        {/* QAM Header Bar */}
        <div
          style={{
            height: "44px",
            flexShrink: 0,
            padding: "0 12px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            borderBottom: "1px solid rgba(255, 255, 255, 0.08)",
            background: "rgba(18, 25, 35, 0.95)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <FaChevronLeft size={11} color={COLORS.textSecondary} />
            <SwitchJoyConIcon size={17} />
            <span style={{ fontSize: "13px", fontWeight: 700, letterSpacing: "0.02em" }}>
              SwitchDeck
            </span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <span
              style={{
                fontSize: "10px",
                fontWeight: 700,
                color: COLORS.textSecondary,
                background: "rgba(255,255,255,0.06)",
                padding: "2px 6px",
                borderRadius: "4px",
              }}
            >
              v0.2.0
            </span>
            <FaEllipsisH size={12} color={COLORS.textSecondary} />
          </div>
        </div>

        {/* Scrollable 340px Inner QAM Content */}
        <div
          style={{
            flex: 1,
            overflowY: "auto",
            overflowX: "hidden",
            padding: "10px",
            boxSizing: "border-box",
          }}
        >
          <QuickAccessPanel
            key={scenarioKey}
            transport={transport}
            initialStatus={status}
            initialProfile={profile}
            initialScrollSection={baseScenario.scrollSection}
          />
        </div>
      </aside>
    </div>
  );
};

const rootEl = document.getElementById("root");
if (rootEl) {
  createRoot(rootEl).render(<PreviewApp />);
}
