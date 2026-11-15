export type TvDriverKind = "cec" | "samsung_tizen" | "roku_ecp" | "webhook" | "none";

export interface OutputModeInfo {
  width: number;
  height: number;
  refresh_hz: number;
  preferred: boolean;
}

export interface ControllerInfo {
  input_name: string;
  name: string;
  vendor_id: string;
  product_id: string;
  transport: string;
  sysfs_path?: string;
  event_dev?: string | null;
  is_actively_awake?: boolean;
  wakeup_count?: number;
}

export interface UnhandledDongleWarning {
  usb_id: string;
  device_name: string;
  sysfs_path: string;
  remediation: string;
}

export interface ScalingInfo {
  target_width: number;
  target_height: number;
  scaling_filter: string | number;
  scaling_scaler: string | number;
  fsr_sharpness: number;
  allow_super_res?: boolean;
  enable_vrr: boolean;
  reason: string;
}

export interface TransitionPayload {
  seq: number;
  kind: "docked" | "undocked";
  display_name: string;
  output_mode: string | null;
  vrr_enabled: boolean;
  p1_controller: string;
  scaling_summary: string;
  tdp_watts: number | null;
  charge_limit: number;
  audio_sink: string | null;
}

export interface DaemonStatus {
  deck_model: string;
  is_docked: boolean;
  ac_online: boolean;
  active_connector: string | null;
  active_edid_id: string | null;
  selected_output_mode: OutputModeInfo | null;
  builtin_controller_bound: boolean;
  active_controllers: ControllerInfo[];
  sleeping_controllers: ControllerInfo[];
  unhandled_dongles: UnhandledDongleWarning[];
  lcd_bluetooth_wakeup_enabled: boolean;
  charge_limit: number;
  tdp_watts: number | null;
  last_scaling: ScalingInfo | null;
  audio_sink: string | null;
  manual_keep_builtin: boolean;
  travel_charge_override: boolean;
  transition_seq: number;
  last_transition: TransitionPayload | null;
  last_error: string | null;
}

export interface TvDriverConfig {
  driver: TvDriverKind;
  host: string;
  port: number;
  mac_address: string;
  hdmi_input: string;
  webhook_url: string;
  auto_power_on: boolean;
  auto_switch_input: boolean;
}

export interface DockProfile {
  profile_id: string;
  display_name: string;
  preferred_container_width: number;
  preferred_container_height: number;
  fsr_sharpness: number;
  docked_tdp_watts: number;
  handheld_tdp_watts: number;
  docked_charge_limit: number;
  docked_volume: number;
  handheld_volume: number;
  auto_pause_on_undock: boolean;
  adaptive_gpu_downscale: boolean;
  tv: TvDriverConfig;
  tv_paired?: boolean;
  tv_cert_fingerprint?: string;
}

export interface PairSamsungResult {
  ok: boolean;
  host?: string;
  port?: number;
  token_saved?: boolean;
  cert_fingerprint?: string;
  profile?: DockProfile;
  cert_mismatch?: boolean;
  error?: string;
}

export interface SwitchDeckTransport {
  getStatus: () => Promise<DaemonStatus>;
  getActiveProfile: () => Promise<DockProfile>;
  updateProfile: (patch: Record<string, unknown>) => Promise<DockProfile>;
  setKeepBuiltin: (enabled: boolean) => Promise<DaemonStatus>;
  rebindBuiltin: () => Promise<DaemonStatus>;
  setChargeOverride: (enabled: boolean) => Promise<DaemonStatus>;
  nudgeDisplay: () => Promise<{ ok: boolean }>;
  pairSamsungTv: (
    host: string,
    port?: number,
    mac?: string,
    trustNewCert?: boolean,
  ) => Promise<PairSamsungResult>;
  testTvWake: () => Promise<{ ok: boolean }>;
  applyNativeAppResolution?: (
    width: number,
    height: number,
    docked: boolean,
  ) => Promise<boolean>;
}
