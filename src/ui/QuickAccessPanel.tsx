import {
  ButtonItem,
  DropdownItem,
  PanelSection,
  PanelSectionRow,
  SliderField,
  TextField,
  ToggleField,
} from "@decky/ui";
import type { DropdownOption } from "@decky/ui";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { FC } from "react";
import {
  FaBolt,
  FaCheckCircle,
  FaExclamationTriangle,
  FaGamepad,
  FaLock,
  FaPlug,
  FaShieldAlt,
  FaSlidersH,
  FaSyncAlt,
  FaTv,
  FaVolumeUp,
  FaWifi,
} from "react-icons/fa";
import {
  isChimeAndToastEnabled,
  playSwitchClickClack,
  setChimeAndToastEnabled,
} from "./audioChime";
import { COLORS, qamStyles } from "./styles";
import { SwitchJoyConIcon } from "./SwitchToast";
import type {
  DaemonStatus,
  DockProfile,
  SwitchDeckTransport,
  TvDriverKind,
} from "./types";

export interface QuickAccessPanelProps {
  transport: SwitchDeckTransport;
  initialStatus?: DaemonStatus;
  initialProfile?: DockProfile;
  initialScrollSection?: "top" | "scaling" | "tv" | "overclock";
}

interface FeedbackMessage {
  tone: "orange" | "crimson" | "sage";
  text: string;
}

interface OverclockPresetDef {
  key: "lcd_conservative" | "oled_balanced" | "gpu_aaa";
  label: string;
  boost_tdp_watts: number;
  gpu_max_mhz: number;
  cpu_boost: boolean;
}

const OVERCLOCK_PRESETS: OverclockPresetDef[] = [
  {
    key: "lcd_conservative",
    label: "LCD 18W · 1700MHz",
    boost_tdp_watts: 18,
    gpu_max_mhz: 1700,
    cpu_boost: true,
  },
  {
    key: "oled_balanced",
    label: "OLED 20W · 1800MHz",
    boost_tdp_watts: 20,
    gpu_max_mhz: 1800,
    cpu_boost: true,
  },
  {
    key: "gpu_aaa",
    label: "AAA 19W · No Boost",
    boost_tdp_watts: 19,
    gpu_max_mhz: 1800,
    cpu_boost: false,
  },
];

const CONTAINER_PRESETS: Array<{ key: string; width: number; height: number; label: string }> = [
  { key: "1920x1080", width: 1920, height: 1080, label: "1920x1080 (1080p Full HD)" },
  { key: "2560x1440", width: 2560, height: 1440, label: "2560x1440 (1440p QHD)" },
  { key: "1280x720", width: 1280, height: 720, label: "1280x720 (720p Perf)" },
];

const TV_DRIVER_OPTIONS: DropdownOption[] = [
  { data: "cec", label: "HDMI-CEC (Official Dock)" },
  { data: "samsung_tizen", label: "Samsung Tizen Wi-Fi (S90C)" },
  { data: "roku_ecp", label: "Roku TV (ECP LAN)" },
  { data: "webhook", label: "Home Assistant / Webhook" },
  { data: "none", label: "Disabled" },
];

function formatDeckModelLabel(model: string): string {
  if (model === "Jupiter") return "Deck LCD";
  if (model === "Galileo") return "Deck OLED";
  return model || "SteamOS";
}

function formatModeLabel(status: DaemonStatus): string {
  if (!status.selected_output_mode) {
    return status.is_docked ? status.active_connector || "External Display" : "1280x800@60Hz";
  }
  const m = status.selected_output_mode;
  return `${m.width}x${m.height}@${Math.round(m.refresh_hz)}Hz`;
}

function formatScalingSummary(status: DaemonStatus): string {
  const s = status.last_scaling;
  if (!s) return "Auto";
  const filter = String(s.scaling_filter || "LINEAR");
  return `${s.target_width}x${s.target_height} · ${filter} (Sharp ${s.fsr_sharpness})`;
}

function shortFingerprint(fp: string): string {
  if (!fp) return "";
  if (fp.length <= 18) return fp;
  return `${fp.slice(0, 10)}...${fp.slice(-8)}`;
}

const HeroStatusCard: FC<{
  status: DaemonStatus;
  profile: DockProfile | null;
  busy: boolean;
  onRefresh: () => void;
}> = ({ status, profile, busy, onRefresh }) => {
  const primaryExternal = status.active_controllers[0];
  const controllerPrimary = primaryExternal
    ? `${primaryExternal.name}`
    : status.builtin_controller_bound
      ? "Steam Deck (28de:1205)"
      : "No Active Gamepad";

  const controllerSubParts: string[] = [];
  if (primaryExternal) {
    controllerSubParts.push(
      status.builtin_controller_bound ? "P1 Ext + Deck Bound" : "P1 Ext · Deck Unbound",
    );
  } else {
    controllerSubParts.push(status.builtin_controller_bound ? "Built-in Bound" : "Unbound");
  }
  if (status.sleeping_controllers.length > 0) {
    controllerSubParts.push(`${status.sleeping_controllers.length} sleeping`);
  }

  const displayName = status.is_docked
    ? profile?.display_name || status.active_connector || "External Display"
    : "Built-in Display";
  const powerLabel = `${status.tdp_watts ?? "--"}W ${status.overclock_active ? "OC" : "TDP"} · ${
    status.charge_limit > 0 ? `${status.charge_limit}% Cap` : "100% Cap"
  }`;
  const powerSubParts: string[] = [];
  if (status.apu_temp_c != null) {
    powerSubParts.push(`${status.apu_temp_c.toFixed(1)}°C APU`);
  }
  if (status.deck_model === "Jupiter") {
    powerSubParts.push(`BT Wake: ${status.lcd_bluetooth_wakeup_enabled ? "Armed" : "Off"}`);
  }

  return (
    <div style={qamStyles.heroCard(status.is_docked)}>
      <div style={qamStyles.heroHeader}>
        <div style={qamStyles.brandGroup}>
          <SwitchJoyConIcon size={18} />
          <span style={qamStyles.brandTitle}>SwitchDeck</span>
        </div>
        <div style={qamStyles.pillRow}>
          <span style={qamStyles.pill("steel")}>{formatDeckModelLabel(status.deck_model)}</span>
          {status.overclock_active && <span style={qamStyles.pill("ochre")}>OC</span>}
          <span style={qamStyles.pill(status.is_docked ? "orangeSolid" : "steel")}>
            {status.is_docked ? "Docked" : "Handheld"}
          </span>
          <button
            type="button"
            aria-label="Refresh SwitchDeck status"
            disabled={busy}
            onClick={onRefresh}
            style={{
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              width: "22px",
              height: "22px",
              borderRadius: "3px",
              border: `1px solid ${COLORS.borderSubtle}`,
              background: COLORS.bgElevated,
              color: COLORS.textSecondary,
              cursor: busy ? "wait" : "pointer",
              padding: 0,
            }}
          >
            <FaSyncAlt size={10} />
          </button>
        </div>
      </div>

      <div style={qamStyles.statList}>
        <div style={qamStyles.statRow}>
          <span style={qamStyles.statLabel}>
            <FaTv size={11} color={status.is_docked ? COLORS.accent : COLORS.textSecondary} />
            <span>Display</span>
          </span>
          <div style={qamStyles.statValueWrap}>
            <span style={qamStyles.statValue}>{displayName}</span>
            <div style={{ display: "flex", gap: "4px", flexWrap: "wrap", justifyContent: "flex-end" }}>
              <span style={qamStyles.statSub}>{formatModeLabel(status)}</span>
              {status.last_scaling?.enable_vrr && <span style={qamStyles.pill("orange")}>VRR</span>}
              {status.ac_online && <span style={qamStyles.pill("sage")}>AC</span>}
            </div>
          </div>
        </div>

        <div style={qamStyles.statRow}>
          <span style={qamStyles.statLabel}>
            <FaGamepad size={11} color={primaryExternal ? COLORS.accent : COLORS.textSecondary} />
            <span>Player 1</span>
          </span>
          <div style={qamStyles.statValueWrap}>
            <span style={qamStyles.statValue}>{controllerPrimary}</span>
            <span style={qamStyles.statSub}>{controllerSubParts.join(" · ")}</span>
          </div>
        </div>

        <div style={qamStyles.statRow}>
          <span style={qamStyles.statLabel}>
            <FaVolumeUp size={11} color={COLORS.textSecondary} />
            <span>Audio</span>
          </span>
          <div style={qamStyles.statValueWrap}>
            <span style={qamStyles.statValue}>{status.audio_sink || "System Default"}</span>
          </div>
        </div>

        <div style={qamStyles.statRow}>
          <span style={qamStyles.statLabel}>
            <FaSlidersH size={11} color={COLORS.textSecondary} />
            <span>Scaling</span>
          </span>
          <div style={qamStyles.statValueWrap}>
            <span style={qamStyles.statValue}>{formatScalingSummary(status)}</span>
            {status.last_scaling?.reason && (
              <span style={qamStyles.statSub}>{status.last_scaling.reason}</span>
            )}
          </div>
        </div>

        <div style={{ ...qamStyles.statRow, borderBottom: "none" }}>
          <span style={qamStyles.statLabel}>
            <FaBolt
              size={11}
              color={
                status.overclock_thermal_throttled
                  ? COLORS.crimson
                  : status.overclock_active || status.travel_charge_override
                    ? COLORS.ochre
                    : COLORS.sage
              }
            />
            <span>Power</span>
          </span>
          <div style={qamStyles.statValueWrap}>
            <span style={qamStyles.statValue}>{powerLabel}</span>
            {powerSubParts.length > 0 && (
              <span style={qamStyles.statSub}>{powerSubParts.join(" · ")}</span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

const DiagnosticWarningBanner: FC<{ status: DaemonStatus }> = ({ status }) => {
  if (
    status.unhandled_dongles.length === 0 &&
    !status.last_error &&
    !status.overclock_thermal_throttled
  ) {
    return null;
  }

  return (
    <div style={qamStyles.warningCard}>
      <div style={qamStyles.warningHeader}>
        <FaExclamationTriangle size={12} />
        <span>Hardware / Driver Alert</span>
      </div>
      <div style={qamStyles.warningBody}>
        {status.overclock_thermal_throttled && (
          <div style={{ marginBottom: "5px" }}>
            <div style={{ fontWeight: 700, color: COLORS.ochre }}>
              Thermal Watchdog Active (&lt;= 15W)
            </div>
            <div style={{ color: COLORS.textSecondary }}>
              APU reached &gt;= 90°C. Docked Overclock automatically stepped down to safe stock
              power until cooling below 80°C.
            </div>
          </div>
        )}
        {status.unhandled_dongles.map((dongle) => (
          <div key={`${dongle.usb_id}-${dongle.sysfs_path}`} style={{ marginBottom: "5px" }}>
            <div style={{ fontWeight: 700, color: COLORS.textPrimary }}>
              [{dongle.usb_id}] {dongle.device_name}
            </div>
            <div style={{ color: COLORS.textSecondary }}>{dongle.remediation}</div>
          </div>
        ))}
        {status.last_error && (
          <div style={{ color: "#f2b8b5" }}>Daemon notice: {status.last_error}</div>
        )}
      </div>
    </div>
  );
};

export const QuickAccessPanel: FC<QuickAccessPanelProps> = ({
  transport,
  initialStatus,
  initialProfile,
  initialScrollSection,
}) => {
  const [status, setStatus] = useState<DaemonStatus | null>(initialStatus ?? null);
  const [profile, setProfile] = useState<DockProfile | null>(initialProfile ?? null);
  const [loading, setLoading] = useState<boolean>(!initialStatus);
  const [busy, setBusy] = useState<boolean>(false);
  const [chimeEnabled, setChimeEnabled] = useState<boolean>(() => isChimeAndToastEnabled());
  const [feedback, setFeedback] = useState<FeedbackMessage | null>(null);
  const [certMismatch, setCertMismatch] = useState<boolean>(false);

  // Local drafts so sliders & text inputs stay fluid
  const [fsrDraft, setFsrDraft] = useState<number>(initialProfile?.fsr_sharpness ?? 2);
  const [dockedTdpDraft, setDockedTdpDraft] = useState<number>(initialProfile?.docked_tdp_watts ?? 15);
  const [handheldTdpDraft, setHandheldTdpDraft] = useState<number>(
    initialProfile?.handheld_tdp_watts ?? 11,
  );
  const [tvHostDraft, setTvHostDraft] = useState<string>(initialProfile?.tv.host ?? "");
  const [tvMacDraft, setTvMacDraft] = useState<string>(initialProfile?.tv.mac_address ?? "");
  const [tvWebhookDraft, setTvWebhookDraft] = useState<string>(
    initialProfile?.tv.webhook_url ?? "",
  );
  const [boostTdpDraft, setBoostTdpDraft] = useState<number>(
    initialProfile?.overclock?.boost_tdp_watts ?? 18,
  );
  const [gpuMaxDraft, setGpuMaxDraft] = useState<number>(() => {
    const mhz = initialProfile?.overclock?.gpu_max_mhz ?? 0;
    return mhz >= 1600 ? mhz : 1600;
  });

  const sliderDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const scalingSectionRef = useRef<HTMLDivElement | null>(null);
  const tvSectionRef = useRef<HTMLDivElement | null>(null);
  const overclockSectionRef = useRef<HTMLDivElement | null>(null);

  const syncProfileDrafts = useCallback((nextProf: DockProfile) => {
    setProfile(nextProf);
    setFsrDraft(nextProf.fsr_sharpness);
    setDockedTdpDraft(nextProf.docked_tdp_watts);
    setHandheldTdpDraft(nextProf.handheld_tdp_watts);
    setTvHostDraft(nextProf.tv?.host ?? "");
    setTvMacDraft(nextProf.tv?.mac_address ?? "");
    setTvWebhookDraft(nextProf.tv?.webhook_url ?? "");
    setBoostTdpDraft(nextProf.overclock?.boost_tdp_watts ?? 18);
    const nextGpu = nextProf.overclock?.gpu_max_mhz ?? 0;
    setGpuMaxDraft(nextGpu >= 1600 ? nextGpu : 1600);
  }, []);

  const refreshAll = useCallback(async () => {
    setBusy(true);
    try {
      const [nextStatus, nextProfile] = await Promise.all([
        transport.getStatus(),
        transport.getActiveProfile(),
      ]);
      setStatus(nextStatus);
      syncProfileDrafts(nextProfile);
    } catch (err) {
      setFeedback({
        tone: "crimson",
        text: `Failed refreshing status: ${err instanceof Error ? err.message : String(err)}`,
      });
    } finally {
      setLoading(false);
      setBusy(false);
    }
  }, [syncProfileDrafts, transport]);

  useEffect(() => {
    if (!initialStatus || !initialProfile) {
      void refreshAll();
    }
    return () => {
      if (sliderDebounceRef.current) {
        clearTimeout(sliderDebounceRef.current);
      }
    };
  }, [initialProfile, initialStatus, refreshAll]);

  useEffect(() => {
    if (initialScrollSection === "scaling" && scalingSectionRef.current) {
      scalingSectionRef.current.scrollIntoView({ block: "start" });
    } else if (initialScrollSection === "tv" && tvSectionRef.current) {
      tvSectionRef.current.scrollIntoView({ block: "start" });
    } else if (initialScrollSection === "overclock" && overclockSectionRef.current) {
      overclockSectionRef.current.scrollIntoView({ block: "start" });
    }
  }, [initialScrollSection]);

  const commitProfilePatch = useCallback(
    async (patch: Record<string, unknown>, message?: string) => {
      setBusy(true);
      try {
        const updated = await transport.updateProfile(patch);
        syncProfileDrafts(updated);
        const refreshed = await transport.getStatus();
        setStatus(refreshed);
        if (message) {
          setFeedback({ tone: "orange", text: message });
        }
      } catch (err) {
        setFeedback({
          tone: "crimson",
          text: err instanceof Error ? err.message : String(err),
        });
      } finally {
        setBusy(false);
      }
    },
    [syncProfileDrafts, transport],
  );

  const scheduleSliderPatch = useCallback(
    (patch: Record<string, unknown>) => {
      if (sliderDebounceRef.current) {
        clearTimeout(sliderDebounceRef.current);
      }
      sliderDebounceRef.current = setTimeout(() => {
        void commitProfilePatch(patch);
      }, 220);
    },
    [commitProfilePatch],
  );

  const containerOptions: DropdownOption[] = useMemo(() => {
    const opts: DropdownOption[] = CONTAINER_PRESETS.map((p) => ({
      data: p.key,
      label: p.label,
    }));
    if (profile) {
      const currentKey = `${profile.preferred_container_width}x${profile.preferred_container_height}`;
      if (!CONTAINER_PRESETS.some((p) => p.key === currentKey)) {
        opts.unshift({ data: currentKey, label: `${currentKey} (Custom)` });
      }
    }
    return opts;
  }, [profile]);

  const selectedContainerKey = profile
    ? `${profile.preferred_container_width}x${profile.preferred_container_height}`
    : "1920x1080";

  const handleContainerChange = (option: DropdownOption) => {
    const raw = String(option.data || "1920x1080");
    const [wStr, hStr] = raw.split("x");
    const width = Number.parseInt(wStr, 10);
    const height = Number.parseInt(hStr, 10);
    if (!Number.isFinite(width) || !Number.isFinite(height)) return;
    void commitProfilePatch(
      { preferred_container_width: width, preferred_container_height: height },
      `Target container set to ${width}x${height}`,
    );
  };

  const handleKeepBuiltinToggle = async (checked: boolean) => {
    setBusy(true);
    try {
      const next = await transport.setKeepBuiltin(checked);
      setStatus(next);
      setFeedback({
        tone: "orange",
        text: checked ? "Built-in Deck controls kept active" : "Smart P1 auto-handoff enabled",
      });
    } catch (err) {
      setFeedback({ tone: "crimson", text: String(err) });
    } finally {
      setBusy(false);
    }
  };

  const handleChargeOverrideToggle = async (checked: boolean) => {
    setBusy(true);
    try {
      const next = await transport.setChargeOverride(checked);
      setStatus(next);
      setFeedback({
        tone: checked ? "orange" : "sage",
        text: checked ? "Travel Charge 100% active until undock" : "80% battery cap restored",
      });
    } catch (err) {
      setFeedback({ tone: "crimson", text: String(err) });
    } finally {
      setBusy(false);
    }
  };

  const handleChimeToggle = (checked: boolean) => {
    setChimeEnabled(checked);
    setChimeAndToastEnabled(checked);
    if (checked) {
      playSwitchClickClack(status?.is_docked ? "docked" : "undocked");
    }
  };

  const handleAutoNativeAppRes = async () => {
    if (!transport.applyNativeAppResolution) {
      setFeedback({
        tone: "crimson",
        text: "Native SteamClient app override unavailable here",
      });
      return;
    }
    const targetW = profile?.preferred_container_width ?? 1920;
    const targetH = profile?.preferred_container_height ?? 1080;
    const dockedNow = Boolean(status?.is_docked);
    const applied = await transport.applyNativeAppResolution(targetW, targetH, dockedNow);
    setFeedback(
      applied
        ? {
            tone: "sage",
            text: dockedNow
              ? `Synced Steam app override to ${targetW}x${targetH}`
              : "Restored Steam app resolution to Default",
          }
        : {
            tone: "crimson",
            text: "No running Steam app or SteamClient unavailable",
          },
    );
  };

  const handleNudgeDisplay = async () => {
    setBusy(true);
    try {
      const res = await transport.nudgeDisplay();
      setFeedback({
        tone: res.ok ? "sage" : "crimson",
        text: res.ok
          ? "Sent GAMESCOPE_DISPLAY_MODE_NUDGE to HDMI output"
          : "Display nudge returned false (no active Gamescope display)",
      });
    } finally {
      setBusy(false);
    }
  };

  const handleRebindBuiltin = async () => {
    setBusy(true);
    try {
      const next = await transport.rebindBuiltin();
      setStatus(next);
      setFeedback({
        tone: "sage",
        text: "Emergency rebind complete: Deck controls (28de:1205) restored",
      });
    } catch (err) {
      setFeedback({ tone: "crimson", text: String(err) });
    } finally {
      setBusy(false);
    }
  };

  const handlePairSamsung = async (trustNewCert: boolean) => {
    const cleanHost = tvHostDraft.trim();
    if (!cleanHost) {
      setFeedback({ tone: "crimson", text: "Enter TV IP/Hostname before pairing" });
      return;
    }
    setBusy(true);
    setCertMismatch(false);
    try {
      const res = await transport.pairSamsungTv(
        cleanHost,
        profile?.tv?.port || 8002,
        tvMacDraft.trim(),
        trustNewCert,
      );
      if (res.ok) {
        if (res.profile) {
          syncProfileDrafts(res.profile);
        } else {
          await refreshAll();
        }
        setFeedback({
          tone: "sage",
          text: res.token_saved
            ? `Samsung TV paired & TLS cert pinned (${cleanHost})`
            : `Connected to ${cleanHost} — accept Allow prompt on TV`,
        });
      } else {
        setCertMismatch(Boolean(res.cert_mismatch));
        setFeedback({
          tone: "crimson",
          text: res.error || "Samsung TV pairing failed",
        });
      }
    } catch (err) {
      setFeedback({ tone: "crimson", text: String(err) });
    } finally {
      setBusy(false);
    }
  };

  const handleTestTvWake = async () => {
    if (!profile) return;
    setBusy(true);
    try {
      const tvPatch: Record<string, unknown> = {
        driver: profile.tv.driver,
        host: tvHostDraft.trim(),
        mac_address: tvMacDraft.trim(),
        webhook_url: tvWebhookDraft.trim(),
      };
      const updated = await transport.updateProfile({ tv: tvPatch });
      syncProfileDrafts(updated);
      const res = await transport.testTvWake();
      setFeedback({
        tone: res.ok ? "sage" : "crimson",
        text: res.ok
          ? "TV wake & input switch signal sent"
          : "TV wake failed — check TV power/network/driver config",
      });
    } catch (err) {
      setFeedback({ tone: "crimson", text: String(err) });
    } finally {
      setBusy(false);
    }
  };

  if (loading && !status) {
    return (
      <div style={qamStyles.root}>
        <div style={qamStyles.heroCard(false)}>Loading SwitchDeck hardware state...</div>
      </div>
    );
  }

  const activeDriver: TvDriverKind = profile?.tv?.driver ?? "cec";
  const hasCertPin = Boolean(profile?.tv_cert_fingerprint);
  const oc = profile?.overclock ?? {
    risk_acknowledged: false,
    enabled: false,
    boost_tdp_watts: 18,
    gpu_max_mhz: 0,
    cpu_boost: true,
  };
  const ocCurrentGpu = oc.gpu_max_mhz >= 1600 ? oc.gpu_max_mhz : 0;
  const matchedOcPreset = OVERCLOCK_PRESETS.find(
    (p) =>
      p.boost_tdp_watts === oc.boost_tdp_watts &&
      p.gpu_max_mhz === ocCurrentGpu &&
      p.cpu_boost === oc.cpu_boost,
  );
  const ocPresetOptions: DropdownOption[] = OVERCLOCK_PRESETS.map((p) => ({
    data: p.key,
    label: p.label,
  }));
  if (!matchedOcPreset) {
    ocPresetOptions.unshift({
      data: "custom",
      label: `Custom (${oc.boost_tdp_watts}W · ${ocCurrentGpu >= 1600 ? `${ocCurrentGpu}MHz` : "Auto"})`,
    });
  }
  const selectedOcPresetKey = matchedOcPreset ? matchedOcPreset.key : "custom";

  const handleOcPresetChange = (opt: DropdownOption) => {
    const preset = OVERCLOCK_PRESETS.find((p) => p.key === String(opt.data));
    if (!preset) return;
    setBoostTdpDraft(preset.boost_tdp_watts);
    setGpuMaxDraft(preset.gpu_max_mhz >= 1600 ? preset.gpu_max_mhz : 1600);
    void commitProfilePatch(
      {
        overclock: {
          boost_tdp_watts: preset.boost_tdp_watts,
          gpu_max_mhz: preset.gpu_max_mhz,
          cpu_boost: preset.cpu_boost,
        },
      },
      `Applied preset: ${preset.label}`,
    );
  };

  let ocPillTone: "ochre" | "crimson" | "steel" = "steel";
  let ocPillLabel = "Stock <= 15W";
  if (status?.overclock_thermal_throttled) {
    ocPillTone = "crimson";
    ocPillLabel = "Thermal Step-Down <= 15W";
  } else if (status?.overclock_active) {
    ocPillTone = "ochre";
    ocPillLabel = "OC Active";
  } else if (oc.enabled && !status?.is_docked) {
    ocPillTone = "steel";
    ocPillLabel = "Standby (Handheld)";
  } else if (oc.enabled && !status?.ac_online) {
    ocPillTone = "crimson";
    ocPillLabel = "Blocked (No AC)";
  }

  return (
    <div style={qamStyles.root}>
      {status && (
        <>
          <HeroStatusCard
            status={status}
            profile={profile}
            busy={busy}
            onRefresh={() => void refreshAll()}
          />
          <DiagnosticWarningBanner status={status} />
        </>
      )}

      {feedback && (
        <div style={qamStyles.inlineFeedback(feedback.tone)} role="status">
          {feedback.text}
        </div>
      )}

      <PanelSection title="Quick Controls & Failsafes">
        <PanelSectionRow>
          <ToggleField
            label="Keep Built-in Controls"
            description="Keep Steam Deck buttons active alongside external P1"
            checked={Boolean(status?.manual_keep_builtin)}
            disabled={busy}
            onChange={(val) => void handleKeepBuiltinToggle(val)}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <ToggleField
            label="Travel Charge 100%"
            description="Override 80% dock cap until undock"
            checked={Boolean(status?.travel_charge_override)}
            disabled={busy}
            onChange={(val) => void handleChargeOverrideToggle(val)}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <ToggleField
            label="Switch Click-Clack HUD"
            description="Play Switch rail chime & transition toast"
            checked={chimeEnabled}
            onChange={handleChimeToggle}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem
            layout="below"
            disabled={busy}
            description={
              status?.is_docked
                ? `Set running Steam app override to ${profile?.preferred_container_width ?? 1920}x${profile?.preferred_container_height ?? 1080}`
                : "Reset running Steam app resolution override"
            }
            onClick={() => void handleAutoNativeAppRes()}
          >
            Sync Native App Resolution
          </ButtonItem>
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={busy} onClick={() => void handleNudgeDisplay()}>
            Fix Blank TV / Nudge HDMI
          </ButtonItem>
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem
            layout="below"
            disabled={busy}
            onClick={() => void handleRebindBuiltin()}
          >
            <span style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}>
              <FaPlug size={11} color={COLORS.accent} />
              <span>Emergency Rebind Deck Controls</span>
            </span>
          </ButtonItem>
        </PanelSectionRow>
      </PanelSection>

      {profile && (
        <>
          <div ref={scalingSectionRef}>
            <PanelSection title="Display & Scaling Profile">
              <PanelSectionRow>
                <DropdownItem
                  label="Container Target"
                  rgOptions={containerOptions}
                  selectedOption={selectedContainerKey}
                  disabled={busy}
                  onChange={handleContainerChange}
                />
              </PanelSectionRow>
              <PanelSectionRow>
                <ToggleField
                  label="Adaptive GPU Step-Down"
                  description="Auto-step container if GPU stays >= 97%"
                  checked={profile.adaptive_gpu_downscale}
                  disabled={busy}
                  onChange={(val) =>
                    void commitProfilePatch({ adaptive_gpu_downscale: val })
                  }
                />
              </PanelSectionRow>
              <PanelSectionRow>
                <SliderField
                  label="FSR Sharpness"
                  value={fsrDraft}
                  min={0}
                  max={20}
                  step={1}
                  showValue
                  disabled={busy}
                  onChange={(val) => {
                    setFsrDraft(val);
                    scheduleSliderPatch({ fsr_sharpness: val });
                  }}
                />
              </PanelSectionRow>
              <PanelSectionRow>
                <SliderField
                  label="Docked TDP"
                  value={Math.min(15, dockedTdpDraft)}
                  min={3}
                  max={15}
                  step={1}
                  valueSuffix="W"
                  showValue
                  disabled={busy}
                  onChange={(val) => {
                    setDockedTdpDraft(val);
                    scheduleSliderPatch({ docked_tdp_watts: val });
                  }}
                />
              </PanelSectionRow>
              <PanelSectionRow>
                <SliderField
                  label="Handheld TDP"
                  value={handheldTdpDraft}
                  min={3}
                  max={15}
                  step={1}
                  valueSuffix="W"
                  showValue
                  disabled={busy}
                  onChange={(val) => {
                    setHandheldTdpDraft(val);
                    scheduleSliderPatch({ handheld_tdp_watts: val });
                  }}
                />
              </PanelSectionRow>
              <PanelSectionRow>
                <ToggleField
                  label="Brief Pause on Undock"
                  description="Pause game briefly while undock settles"
                  checked={profile.auto_pause_on_undock}
                  disabled={busy}
                  onChange={(val) =>
                    void commitProfilePatch({ auto_pause_on_undock: val })
                  }
                />
              </PanelSectionRow>
            </PanelSection>
          </div>

          <div ref={tvSectionRef}>
            <PanelSection title="Smart TV Bridge">
              <PanelSectionRow>
                <DropdownItem
                  label="TV Driver"
                  rgOptions={TV_DRIVER_OPTIONS}
                  selectedOption={activeDriver}
                  disabled={busy}
                  onChange={(opt) => {
                    const nextDriver = String(opt.data || "none") as TvDriverKind;
                    void commitProfilePatch(
                      { tv: { driver: nextDriver } },
                      `TV driver set to ${opt.label}`,
                    );
                  }}
                />
              </PanelSectionRow>

              {(activeDriver === "samsung_tizen" || activeDriver === "roku_ecp") && (
                <PanelSectionRow>
                  <TextField
                    label="TV Host / IP"
                    placeholder="192.168.1.50"
                    value={tvHostDraft}
                    disabled={busy}
                    onChange={(e) => setTvHostDraft(e.target.value)}
                  />
                </PanelSectionRow>
              )}

              {activeDriver === "samsung_tizen" && (
                <>
                  <PanelSectionRow>
                    <TextField
                      label="TV MAC (WoL)"
                      placeholder="AA:BB:CC:DD:EE:FF"
                      value={tvMacDraft}
                      disabled={busy}
                      onChange={(e) => setTvMacDraft(e.target.value)}
                    />
                  </PanelSectionRow>

                  {(hasCertPin || profile.tv_paired) && (
                    <PanelSectionRow>
                      <div style={qamStyles.certCard}>
                        <div
                          style={{
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "space-between",
                            gap: "6px",
                            flexWrap: "wrap",
                          }}
                        >
                          <span
                            style={{
                              display: "inline-flex",
                              alignItems: "center",
                              gap: "5px",
                              fontSize: "11px",
                              fontWeight: 700,
                              color: COLORS.sage,
                            }}
                          >
                            <FaShieldAlt size={11} />
                            <span>TLS Cert Pin Active</span>
                          </span>
                          <div style={{ display: "flex", gap: "4px" }}>
                            {profile.tv_paired && (
                              <span style={qamStyles.pill("sage")}>
                                <FaCheckCircle size={9} />
                                <span>Paired</span>
                              </span>
                            )}
                            {hasCertPin && (
                              <span style={qamStyles.pill("steel")}>
                                <FaLock size={9} />
                                <span>TOFU Pinned</span>
                              </span>
                            )}
                          </div>
                        </div>
                        {profile.tv_cert_fingerprint && (
                          <span style={qamStyles.monoCode}>
                            sha256: {shortFingerprint(profile.tv_cert_fingerprint)}
                          </span>
                        )}
                      </div>
                    </PanelSectionRow>
                  )}

                  {certMismatch && (
                    <PanelSectionRow>
                      <ButtonItem
                        layout="below"
                        disabled={busy}
                        onClick={() => void handlePairSamsung(true)}
                      >
                        Trust New TV Cert & Re-Pair
                      </ButtonItem>
                    </PanelSectionRow>
                  )}

                  <PanelSectionRow>
                    <ButtonItem
                      layout="below"
                      disabled={busy}
                      onClick={() => void handlePairSamsung(false)}
                    >
                      <span style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}>
                        <FaWifi size={11} color={COLORS.accent} />
                        <span>Pair Samsung TV</span>
                      </span>
                    </ButtonItem>
                  </PanelSectionRow>
                </>
              )}

              {activeDriver === "webhook" && (
                <PanelSectionRow>
                  <TextField
                    label="Webhook URL"
                    placeholder="http://homeassistant.local:8123/api/webhook/switchdeck"
                    value={tvWebhookDraft}
                    disabled={busy}
                    onChange={(e) => setTvWebhookDraft(e.target.value)}
                  />
                </PanelSectionRow>
              )}

              {activeDriver !== "none" && (
                <PanelSectionRow>
                  <ButtonItem layout="below" disabled={busy} onClick={() => void handleTestTvWake()}>
                    Test TV Wake
                  </ButtonItem>
                </PanelSectionRow>
              )}
            </PanelSection>
          </div>

          <div ref={overclockSectionRef}>
            <PanelSection title="Experimental: Docked Overclock">
              {!oc.risk_acknowledged ? (
                <>
                  <PanelSectionRow>
                    <div style={qamStyles.overclockWarningCard}>
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: "6px",
                          color: COLORS.ochre,
                          fontSize: "11.5px",
                          fontWeight: 700,
                          marginBottom: "4px",
                        }}
                      >
                        <FaExclamationTriangle size={12} />
                        <span>Experimental Power &amp; Clock Warning</span>
                      </div>
                      <div style={qamStyles.warningBody}>
                        <div style={{ marginBottom: "3px" }}>
                          <strong>Volatile sysfs only:</strong> zero BIOS/NVRAM edits, zero
                          undervolting or memory timing writes (avoids idle C-state crashes).
                        </div>
                        <div style={{ marginBottom: "3px" }}>
                          <strong>Thermals &amp; PD supply:</strong> raises sustained heat and fan
                          noise. Use a 45W-65W+ PD charger when boosting through a USB-C hub.
                        </div>
                        <div>
                          <strong>Guardrails:</strong> hard-capped at 22W / 2000 MHz (community safe:
                          18-19W LCD, 19-22W OLED), requires AC power, steps down at &gt;= 90°C, and
                          resets to stock on undock. You assume thermal &amp; hardware risk.
                        </div>
                      </div>
                    </div>
                  </PanelSectionRow>
                  <PanelSectionRow>
                    <ButtonItem
                      layout="below"
                      disabled={busy}
                      onClick={() =>
                        void commitProfilePatch(
                          { overclock: { risk_acknowledged: true } },
                          "Experimental docked overclock unlocked (disabled until toggled on)",
                        )
                      }
                    >
                      <span style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}>
                        <FaBolt size={11} color={COLORS.ochre} />
                        <span>I Understand — Unlock Experimental Controls</span>
                      </span>
                    </ButtonItem>
                  </PanelSectionRow>
                </>
              ) : (
                <>
                  <PanelSectionRow>
                    <div style={qamStyles.telemetryCard}>
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "space-between",
                          gap: "6px",
                          flexWrap: "wrap",
                        }}
                      >
                        <span style={qamStyles.pill(ocPillTone)}>
                          <FaBolt size={9} />
                          <span>{ocPillLabel}</span>
                        </span>
                        <span style={qamStyles.statSub}>
                          APU{" "}
                          {status?.apu_temp_c != null ? `${status.apu_temp_c.toFixed(0)}°C` : "--"}{" "}
                          · SMU {status?.hw_max_tdp_watts ?? 22}W
                        </span>
                      </div>
                      <div style={{ fontSize: "10.5px", color: COLORS.textPrimary, fontWeight: 600 }}>
                        {status?.overclock_status_note ||
                          `Target ${boostTdpDraft}W · ${gpuMaxDraft <= 1600 ? "GPU Stock Auto" : `GPU 400-${gpuMaxDraft} MHz`} · CPU Boost ${oc.cpu_boost ? "On" : "Off"}`}
                      </div>
                      <div style={{ fontSize: "10px", color: COLORS.textSecondary, lineHeight: 1.35 }}>
                        45W-65W+ PD charger recommended on hubs · Auto-steps &lt;= 15W at &gt;=
                        90°C
                      </div>
                    </div>
                  </PanelSectionRow>

                  <PanelSectionRow>
                    <DropdownItem
                      label="Preset"
                      rgOptions={ocPresetOptions}
                      selectedOption={selectedOcPresetKey}
                      disabled={busy}
                      onChange={handleOcPresetChange}
                    />
                  </PanelSectionRow>

                  <PanelSectionRow>
                    <ToggleField
                      label="Enable Docked Overclock"
                      description="Applies only when docked on AC; auto-resets on undock or >= 90°C limit"
                      checked={oc.enabled}
                      disabled={busy}
                      onChange={(val) =>
                        void commitProfilePatch(
                          { overclock: { enabled: val } },
                          val
                            ? status?.is_docked
                              ? status.ac_online
                                ? "Experimental docked overclock active"
                                : "Overclock armed (waiting for AC power)"
                              : "Overclock armed (applies when docked on AC)"
                            : "Overclock disabled — restored stock <= 15W",
                        )
                      }
                    />
                  </PanelSectionRow>

                  <PanelSectionRow>
                    <SliderField
                      label="Boost Sustained TDP"
                      value={boostTdpDraft}
                      min={15}
                      max={22}
                      step={1}
                      valueSuffix="W"
                      showValue
                      disabled={busy}
                      onChange={(val) => {
                        setBoostTdpDraft(val);
                        scheduleSliderPatch({ overclock: { boost_tdp_watts: val } });
                      }}
                    />
                  </PanelSectionRow>

                  <PanelSectionRow>
                    <SliderField
                      label={gpuMaxDraft <= 1600 ? "Max GPU Clock (Stock Auto)" : "Max GPU Clock (400+)"}
                      value={gpuMaxDraft}
                      min={1600}
                      max={2000}
                      step={50}
                      valueSuffix=" MHz"
                      showValue
                      disabled={busy}
                      onChange={(val) => {
                        setGpuMaxDraft(val);
                        scheduleSliderPatch({
                          overclock: { gpu_max_mhz: val <= 1600 ? 0 : val },
                        });
                      }}
                    />
                  </PanelSectionRow>

                  <PanelSectionRow>
                    <ToggleField
                      label="Docked CPU Turbo Boost"
                      description="Turn off in GPU-bound AAA titles to leave more SMU power headroom for GPU"
                      checked={oc.cpu_boost}
                      disabled={busy}
                      onChange={(val) =>
                        void commitProfilePatch(
                          { overclock: { cpu_boost: val } },
                          val
                            ? "Docked CPU turbo boost enabled"
                            : "Docked CPU turbo boost disabled for GPU power headroom",
                        )
                      }
                    />
                  </PanelSectionRow>

                  <PanelSectionRow>
                    <ButtonItem
                      layout="below"
                      disabled={busy}
                      onClick={() => {
                        setBoostTdpDraft(15);
                        setGpuMaxDraft(1600);
                        void commitProfilePatch(
                          {
                            overclock: {
                              risk_acknowledged: false,
                              enabled: false,
                              boost_tdp_watts: 15,
                              gpu_max_mhz: 0,
                              cpu_boost: true,
                            },
                          },
                          "Overclock reset to stock 15W and controls locked",
                        );
                      }}
                    >
                      <span style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}>
                        <FaLock size={11} color={COLORS.crimson} />
                        <span>Reset &amp; Lock Overclock Controls</span>
                      </span>
                    </ButtonItem>
                  </PanelSectionRow>
                </>
              )}
            </PanelSection>
          </div>
        </>
      )}
    </div>
  );
};
