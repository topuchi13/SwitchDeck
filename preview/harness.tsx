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

type ScenarioKey = "handheld" | "docked_s90c" | "docked_warning" | "tv_pairing" | "docked_overclock";

interface ScenarioData {
  key: ScenarioKey;
  label: string;
  resolutionLabel: string;
  status: DaemonStatus;
  profile: DockProfile;
  toast: TransitionPayload | null;
  scrollSection: "top" | "scaling" | "tv" | "overclock";
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
      apu_temp_c: 48.0,
      hw_max_tdp_watts: 19,
      overclock_active: false,
      overclock_thermal_throttled: false,
      overclock_status_note: null,
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
      apu_temp_c: 62.0,
      hw_max_tdp_watts: 22,
      overclock_active: false,
      overclock_thermal_throttled: false,
      overclock_status_note: null,
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
      apu_temp_c: 64.0,
      hw_max_tdp_watts: 19,
      overclock_active: false,
      overclock_thermal_throttled: false,
      overclock_status_note: null,
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
      apu_temp_c: 59.0,
      hw_max_tdp_watts: 22,
      overclock_active: false,
      overclock_thermal_throttled: false,
      overclock_status_note: null,
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

  docked_overclock: {
    key: "docked_overclock",
    label: "Docked OC (20W)",
    resolutionLabel: "1920x1080",
    scrollSection: "overclock",
    toast: {
      seq: 5,
      kind: "docked",
      display_name: "SAMSUNG S90C",
      output_mode: "2560x1440@120Hz",
      vrr_enabled: true,
      p1_controller: "Xbox Wireless Controller",
      scaling_summary: "1080p · FSR (Sharp 2)",
      tdp_watts: 20,
      charge_limit: 80,
      audio_sink: "HDMI · SAMSUNG S90C",
      overclock_active: true,
    },
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
          input_name: "input14",
          name: "Xbox Wireless Controller (2.4GHz)",
          vendor_id: "045e",
          product_id: "02ea",
          transport: "dongle_24g",
          is_actively_awake: true,
          wakeup_count: 1,
        },
      ],
      sleeping_controllers: [],
      unhandled_dongles: [],
      lcd_bluetooth_wakeup_enabled: false,
      charge_limit: 80,
      tdp_watts: 20,
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
      transition_seq: 5,
      last_transition: null,
      last_error: null,
      apu_temp_c: 71.0,
      hw_max_tdp_watts: 22,
      overclock_active: true,
      overclock_thermal_throttled: false,
      overclock_status_note: "Active: 20W sustained · GPU 400-1800 MHz · CPU Boost On",
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
      overclock: {
        risk_acknowledged: true,
        enabled: true,
        boost_tdp_watts: 20,
        gpu_max_mhz: 1800,
        cpu_boost: true,
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
      background: "linear-gradient(160deg, #131416 0%, #191816 58%, #151412 100%)",
      overflow: "hidden",
    }}
  >
    {/* Matte dark architectural topographic & display calibration vector backdrop */}
    <svg
      viewBox="0 0 1280 720"
      preserveAspectRatio="xMidYMid slice"
      style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}
      aria-hidden="true"
    >
      <defs>
        <pattern id="calibGrid" width="64" height="64" patternUnits="userSpaceOnUse">
          <path d="M 64 0 L 0 0 0 64" fill="none" stroke="#222429" strokeWidth="1" />
        </pattern>
      </defs>
      <rect width="1280" height="720" fill="url(#calibGrid)" opacity="0.65" />

      {/* Subtle topographic horizon ridgelines */}
      <path
        d="M0 490 Q240 430 480 468 T960 442 T1280 470"
        fill="none"
        stroke="#27292f"
        strokeWidth="1.2"
      />
      <path
        d="M0 535 Q300 485 600 520 T1280 505"
        fill="none"
        stroke="#25272c"
        strokeWidth="1.2"
      />
      <path
        d="M0 582 Q360 548 720 574 T1280 560"
        fill="none"
        stroke="#222428"
        strokeWidth="1"
      />
      {/* Horizon datum reference line */}
      <line
        x1="0"
        y1="382"
        x2="1280"
        y2="382"
        stroke="rgba(255, 90, 38, 0.08)"
        strokeWidth="1"
        strokeDasharray="6 6"
      />

      {/* Crisp thin wireframe geometric Triforce emblem (zero blur / glow) */}
      <g transform="translate(460, 326)" opacity="0.55">
        <circle cx="0" cy="48" r="132" fill="none" stroke="#2a2b30" strokeWidth="1" />
        <polygon points="0,-54 -46,24 46,24" fill="none" stroke="#b8893a" strokeWidth="1.5" />
        <polygon points="-46,24 -92,102 0,102" fill="none" stroke="#b8893a" strokeWidth="1.5" />
        <polygon points="46,24 0,102 92,102" fill="none" stroke="#b8893a" strokeWidth="1.5" />
      </g>
    </svg>

    {/* Flat Technical In-Game Viewport Overlay */}
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
              width: "13px",
              height: "13px",
              borderRadius: "2px",
              background: idx < 7 ? "#d9483b" : "#26282e",
              border: `1px solid ${idx < 7 ? "#f0695d" : "#343840"}`,
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
          borderRadius: "3px",
          background: "#181a1e",
          border: "1px solid #32363e",
          color: COLORS.textSecondary,
          fontFamily: COLORS.monoFont,
          fontSize: "10.5px",
          fontWeight: 600,
        }}
      >
        <span style={{ color: "#d4a64a", fontWeight: 700 }}>Zelda64Recompiled</span>
        <span>·</span>
        <span style={{ color: COLORS.textPrimary }}>{activeGameRes}</span>
        <span>·</span>
        <span style={{ color: isDocked ? COLORS.accent : COLORS.steel }}>
          {isDocked ? "16:9 DOCKED" : "16:10 HANDHELD"}
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
        const nextOc = {
          ...(profile.overclock ?? {
            risk_acknowledged: false,
            enabled: false,
            boost_tdp_watts: 18,
            gpu_max_mhz: 0,
            cpu_boost: true,
          }),
          ...((patch.overclock as Partial<NonNullable<DockProfile["overclock"]>>) || {}),
        };
        const nextProf: DockProfile = {
          ...profile,
          ...(patch as Partial<DockProfile>),
          tv: {
            ...profile.tv,
            ...((patch.tv as Partial<DockProfile["tv"]>) || {}),
          },
          overclock: nextOc,
        };
        setProfile(nextProf);
        setStatus((prev) => {
          const ocActive = Boolean(
            nextOc.risk_acknowledged && nextOc.enabled && prev.is_docked && prev.ac_online,
          );
          const nextTdp = ocActive
            ? nextOc.boost_tdp_watts
            : prev.is_docked
              ? nextProf.docked_tdp_watts
              : nextProf.handheld_tdp_watts;
          const gpuNote =
            nextOc.gpu_max_mhz >= 1600 ? `GPU 400-${nextOc.gpu_max_mhz} MHz` : "GPU Stock Auto";
          return {
            ...prev,
            tdp_watts: nextTdp,
            overclock_active: ocActive,
            overclock_status_note: ocActive
              ? `Active: ${nextOc.boost_tdp_watts}W sustained · ${gpuNote} · CPU Boost ${nextOc.cpu_boost ? "On" : "Off"}`
              : null,
          };
        });
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
        background: "#121316",
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
          background: "linear-gradient(180deg, rgba(19, 20, 22, 0.88) 0%, rgba(19, 20, 22, 0) 100%)",
          fontSize: "12px",
          color: COLORS.textSecondary,
          zIndex: 5,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "10px", fontWeight: 600 }}>
          <span style={{ color: COLORS.textPrimary }}>SteamOS 3.7</span>
          <span style={{ color: COLORS.textMuted }}>|</span>
          <span>{baseScenario.label}</span>
        </div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "12px",
            fontWeight: 600,
            fontFamily: COLORS.monoFont,
            fontSize: "11px",
          }}
        >
          <FaWifi size={12} color={COLORS.textSecondary} />
          <span style={{ display: "inline-flex", alignItems: "center", gap: "4px" }}>
            <FaBatteryThreeQuarters size={13} color={COLORS.sage} />
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

      {/* Interactive Scenario Switcher on bottom-left (flat industrial tabs) */}
      <div
        style={{
          position: "absolute",
          bottom: "44px",
          left: "24px",
          right: "380px",
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
                padding: "5px 9px",
                borderRadius: "3px",
                border: `1px solid ${active ? COLORS.accent : "#32363e"}`,
                background: active ? "#25282f" : "rgba(20, 22, 26, 0.92)",
                color: active ? COLORS.textPrimary : COLORS.textSecondary,
                fontFamily: COLORS.monoFont,
                fontSize: "10.5px",
                fontWeight: 600,
                cursor: "pointer",
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
          background: "linear-gradient(0deg, rgba(19, 20, 22, 0.92) 0%, rgba(19, 20, 22, 0) 100%)",
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
          <strong style={{ color: COLORS.accent }}>•••</strong> Quick Access
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
          background: "#181a1e",
          borderLeft: `1px solid ${COLORS.borderSubtle}`,
          boxShadow: "-8px 0 28px rgba(0, 0, 0, 0.55)",
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
            borderBottom: `1px solid ${COLORS.borderSubtle}`,
            background: "#1c1e23",
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
                fontFamily: COLORS.monoFont,
                fontSize: "10px",
                fontWeight: 700,
                color: COLORS.textSecondary,
                background: COLORS.steelSoft,
                border: `1px solid ${COLORS.borderSubtle}`,
                padding: "2px 6px",
                borderRadius: "3px",
              }}
            >
              v0.3.1
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
