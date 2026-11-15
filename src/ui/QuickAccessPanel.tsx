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
  initialScrollSection?: "top" | "scaling" | "tv";
}

interface FeedbackMessage {
  tone: "blue" | "coral" | "emerald";
  text: string;
}

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
  const powerLabel = `${status.tdp_watts ?? "--"}W TDP · ${
    status.charge_limit > 0 ? `${status.charge_limit}% Cap` : "100% Cap"
  }`;

  return (
    <div style={qamStyles.heroCard}>
      <div style={qamStyles.heroHeader}>
        <div style={qamStyles.brandGroup}>
          <SwitchJoyConIcon size={18} />
          <span style={qamStyles.brandTitle}>SwitchDeck</span>
        </div>
        <div style={qamStyles.pillRow}>
          <span style={qamStyles.pill("slate")}>{formatDeckModelLabel(status.deck_model)}</span>
          <span style={qamStyles.pill(status.is_docked ? "blue" : "coral")}>
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
              borderRadius: "6px",
              border: `1px solid ${COLORS.borderSubtle}`,
              background: "rgba(255,255,255,0.04)",
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
            <FaTv size={11} color={status.is_docked ? COLORS.neonBlue : COLORS.neonCoral} />
            <span>Display</span>
          </span>
          <div style={qamStyles.statValueWrap}>
            <span style={qamStyles.statValue}>{displayName}</span>
            <div style={{ display: "flex", gap: "4px", flexWrap: "wrap", justifyContent: "flex-end" }}>
              <span style={qamStyles.statSub}>{formatModeLabel(status)}</span>
              {status.last_scaling?.enable_vrr && <span style={qamStyles.pill("blue")}>VRR</span>}
              {status.ac_online && <span style={qamStyles.pill("emerald")}>AC</span>}
            </div>
          </div>
        </div>

        <div style={qamStyles.statRow}>
          <span style={qamStyles.statLabel}>
            <FaGamepad size={11} color={COLORS.neonBlue} />
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
            <FaSlidersH size={11} color={COLORS.neonBlue} />
            <span>Scaling</span>
          </span>
          <div style={qamStyles.statValueWrap}>
            <span style={qamStyles.statValue}>{formatScalingSummary(status)}</span>
            {status.last_scaling?.reason && (
              <span style={qamStyles.statSub}>{status.last_scaling.reason}</span>
            )}
          </div>
        </div>

        <div style={qamStyles.statRow}>
          <span style={qamStyles.statLabel}>
            <FaBolt size={11} color={status.travel_charge_override ? COLORS.amber : COLORS.emerald} />
            <span>Power</span>
          </span>
          <div style={qamStyles.statValueWrap}>
            <span style={qamStyles.statValue}>{powerLabel}</span>
            {status.deck_model === "Jupiter" && (
              <span style={qamStyles.statSub}>
                LCD BT Wake: {status.lcd_bluetooth_wakeup_enabled ? "Dock Armed" : "Locked Off"}
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

const DiagnosticWarningBanner: FC<{ status: DaemonStatus }> = ({ status }) => {
  if (status.unhandled_dongles.length === 0 && !status.last_error) {
    return null;
  }

  return (
    <div style={qamStyles.warningCard}>
      <div style={qamStyles.warningHeader}>
        <FaExclamationTriangle size={12} />
        <span>Hardware / Driver Alert</span>
      </div>
      <div style={qamStyles.warningBody}>
        {status.unhandled_dongles.map((dongle) => (
          <div key={`${dongle.usb_id}-${dongle.sysfs_path}`} style={{ marginBottom: "5px" }}>
            <div style={{ fontWeight: 700, color: COLORS.textPrimary }}>
              [{dongle.usb_id}] {dongle.device_name}
            </div>
            <div style={{ color: "#cbd5e1" }}>{dongle.remediation}</div>
          </div>
        ))}
        {status.last_error && (
          <div style={{ color: "#fecaca" }}>Daemon notice: {status.last_error}</div>
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

  const sliderDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const scalingSectionRef = useRef<HTMLDivElement | null>(null);
  const tvSectionRef = useRef<HTMLDivElement | null>(null);

  const syncProfileDrafts = useCallback((nextProf: DockProfile) => {
    setProfile(nextProf);
    setFsrDraft(nextProf.fsr_sharpness);
    setDockedTdpDraft(nextProf.docked_tdp_watts);
    setHandheldTdpDraft(nextProf.handheld_tdp_watts);
    setTvHostDraft(nextProf.tv?.host ?? "");
    setTvMacDraft(nextProf.tv?.mac_address ?? "");
    setTvWebhookDraft(nextProf.tv?.webhook_url ?? "");
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
        tone: "coral",
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
          setFeedback({ tone: "blue", text: message });
        }
      } catch (err) {
        setFeedback({
          tone: "coral",
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
        tone: "blue",
        text: checked ? "Built-in Deck controls kept active" : "Smart P1 auto-handoff enabled",
      });
    } catch (err) {
      setFeedback({ tone: "coral", text: String(err) });
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
        tone: checked ? "blue" : "emerald",
        text: checked ? "Travel Charge 100% active until undock" : "80% battery cap restored",
      });
    } catch (err) {
      setFeedback({ tone: "coral", text: String(err) });
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
        tone: "coral",
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
            tone: "emerald",
            text: dockedNow
              ? `Synced Steam app override to ${targetW}x${targetH}`
              : "Restored Steam app resolution to Default",
          }
        : {
            tone: "coral",
            text: "No running Steam app or SteamClient unavailable",
          },
    );
  };

  const handleNudgeDisplay = async () => {
    setBusy(true);
    try {
      const res = await transport.nudgeDisplay();
      setFeedback({
        tone: res.ok ? "emerald" : "coral",
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
        tone: "emerald",
        text: "Emergency rebind complete: Deck controls (28de:1205) restored",
      });
    } catch (err) {
      setFeedback({ tone: "coral", text: String(err) });
    } finally {
      setBusy(false);
    }
  };

  const handlePairSamsung = async (trustNewCert: boolean) => {
    const cleanHost = tvHostDraft.trim();
    if (!cleanHost) {
      setFeedback({ tone: "coral", text: "Enter TV IP/Hostname before pairing" });
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
          tone: "emerald",
          text: res.token_saved
            ? `Samsung TV paired & TLS cert pinned (${cleanHost})`
            : `Connected to ${cleanHost} — accept Allow prompt on TV`,
        });
      } else {
        setCertMismatch(Boolean(res.cert_mismatch));
        setFeedback({
          tone: "coral",
          text: res.error || "Samsung TV pairing failed",
        });
      }
    } catch (err) {
      setFeedback({ tone: "coral", text: String(err) });
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
        tone: res.ok ? "emerald" : "coral",
        text: res.ok
          ? "TV wake & input switch signal sent"
          : "TV wake failed — check TV power/network/driver config",
      });
    } catch (err) {
      setFeedback({ tone: "coral", text: String(err) });
    } finally {
      setBusy(false);
    }
  };

  if (loading && !status) {
    return (
      <div style={qamStyles.root}>
        <div style={qamStyles.heroCard}>Loading SwitchDeck hardware state...</div>
      </div>
    );
  }

  const activeDriver: TvDriverKind = profile?.tv?.driver ?? "cec";
  const hasCertPin = Boolean(profile?.tv_cert_fingerprint);

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
              <FaPlug size={11} color={COLORS.neonCoral} />
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
                  value={dockedTdpDraft}
                  min={3}
                  max={30}
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
                              color: COLORS.emerald,
                            }}
                          >
                            <FaShieldAlt size={11} />
                            <span>TLS Cert Pin Active</span>
                          </span>
                          <div style={{ display: "flex", gap: "4px" }}>
                            {profile.tv_paired && (
                              <span style={qamStyles.pill("emerald")}>
                                <FaCheckCircle size={9} />
                                <span>Paired</span>
                              </span>
                            )}
                            {hasCertPin && (
                              <span style={qamStyles.pill("blue")}>
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
                        <FaWifi size={11} color={COLORS.neonBlue} />
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
        </>
      )}
    </div>
  );
};
