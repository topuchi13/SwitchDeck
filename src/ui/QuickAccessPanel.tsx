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
  isChimeAndToastEnabled,
  playSwitchClickClack,
  setChimeAndToastEnabled,
} from "./audioChime";
import { qamStyles } from "./styles";
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
  tone: "accent" | "crimson" | "sage";
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
  { key: "1920x1080", width: 1920, height: 1080, label: "1080p (1920x1080)" },
  { key: "2560x1440", width: 2560, height: 1440, label: "1440p (2560x1440)" },
  { key: "1280x720", width: 1280, height: 720, label: "720p (1280x720)" },
];

const TV_DRIVER_OPTIONS: DropdownOption[] = [
  { data: "cec", label: "HDMI-CEC" },
  { data: "samsung_tizen", label: "Samsung Tizen (Wi-Fi)" },
  { data: "lg_webos", label: "LG webOS (Wi-Fi)" },
  { data: "sony_bravia", label: "Sony Bravia (PSK)" },
  { data: "roku_ecp", label: "Roku TV (ECP)" },
  { data: "wol", label: "Wake-on-LAN Only" },
  { data: "webhook", label: "Webhook / Home Assistant" },
  { data: "none", label: "Disabled" },
];

const DEFAULT_TV_PORTS: Record<TvDriverKind, number> = {
  cec: 8002,
  samsung_tizen: 8002,
  lg_webos: 3001,
  sony_bravia: 80,
  roku_ecp: 8060,
  wol: 9,
  webhook: 443,
  none: 8002,
};

const HDMI_INPUT_OPTIONS: DropdownOption[] = [
  { data: "HDMI1", label: "HDMI 1" },
  { data: "HDMI2", label: "HDMI 2" },
  { data: "HDMI3", label: "HDMI 3" },
  { data: "HDMI4", label: "HDMI 4" },
  { data: "AV1", label: "AV 1" },
  { data: "Tuner", label: "Tuner" },
];

function parsePortDraft(raw: string, driver: TvDriverKind): number {
  const fallback = DEFAULT_TV_PORTS[driver] ?? 8002;
  const parsed = Number.parseInt(raw.trim(), 10);
  if (!Number.isFinite(parsed) || parsed < 1 || parsed > 65535) {
    return fallback;
  }
  return parsed;
}

function mergeProfilePatch(
  base: Record<string, unknown>,
  incoming: Record<string, unknown>,
): Record<string, unknown> {
  const out: Record<string, unknown> = { ...base, ...incoming };
  if (base.overclock || incoming.overclock) {
    out.overclock = {
      ...((base.overclock as Record<string, unknown> | undefined) || {}),
      ...((incoming.overclock as Record<string, unknown> | undefined) || {}),
    };
  }
  if (base.tv || incoming.tv) {
    out.tv = {
      ...((base.tv as Record<string, unknown> | undefined) || {}),
      ...((incoming.tv as Record<string, unknown> | undefined) || {}),
    };
  }
  return out;
}

function formatModeLabel(status: DaemonStatus): string {
  if (!status.selected_output_mode) {
    return status.is_docked ? status.active_connector || "External Display" : "1280x800@60Hz";
  }
  const m = status.selected_output_mode;
  const base = `${m.width}x${m.height}@${Math.round(m.refresh_hz)}Hz`;
  return status.last_scaling?.enable_vrr ? `${base} VRR` : base;
}

function formatScalingSummary(status: DaemonStatus): string {
  const s = status.last_scaling;
  if (!s) return "Auto";
  const filter = String(s.scaling_filter || "LINEAR");
  return `${s.target_width}x${s.target_height} ${filter} (${s.fsr_sharpness})`;
}

function shortFingerprint(fp: string): string {
  if (!fp) return "";
  if (fp.length <= 18) return fp;
  return `${fp.slice(0, 10)}...${fp.slice(-8)}`;
}

const StatusRow: FC<{ label: string; value: string }> = ({ label, value }) => (
  <PanelSectionRow>
    <div style={qamStyles.statusSummaryRow}>
      <span style={qamStyles.statusKey}>{label}</span>
      <span style={qamStyles.statusVal}>{value}</span>
    </div>
  </PanelSectionRow>
);

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
  const [pairingBusy, setPairingBusy] = useState<boolean>(false);
  const [chimeEnabled, setChimeEnabled] = useState<boolean>(() => isChimeAndToastEnabled());
  const [feedback, setFeedback] = useState<FeedbackMessage | null>(null);
  const [tvFeedback, setTvFeedback] = useState<FeedbackMessage | null>(null);
  const [ocFeedback, setOcFeedback] = useState<FeedbackMessage | null>(null);
  const [certMismatch, setCertMismatch] = useState<boolean>(false);

  const [fsrDraft, setFsrDraft] = useState<number>(initialProfile?.fsr_sharpness ?? 2);
  const [dockedTdpDraft, setDockedTdpDraft] = useState<number>(initialProfile?.docked_tdp_watts ?? 15);
  const [handheldTdpDraft, setHandheldTdpDraft] = useState<number>(
    initialProfile?.handheld_tdp_watts ?? 11,
  );
  const [tvHostDraft, setTvHostDraft] = useState<string>(initialProfile?.tv.host ?? "");
  const [tvPortDraft, setTvPortDraft] = useState<string>(
    String(initialProfile?.tv.port ?? 8002),
  );
  const [tvMacDraft, setTvMacDraft] = useState<string>(initialProfile?.tv.mac_address ?? "");
  const [tvPskDraft, setTvPskDraft] = useState<string>("");
  const [tvWebhookDraft, setTvWebhookDraft] = useState<string>(
    initialProfile?.tv.webhook_url ?? "",
  );
  const [tvDirty, setTvDirty] = useState<boolean>(false);
  const [boostTdpDraft, setBoostTdpDraft] = useState<number>(
    initialProfile?.overclock?.boost_tdp_watts ?? 18,
  );
  const [gpuMaxDraft, setGpuMaxDraft] = useState<number>(() => {
    const mhz = initialProfile?.overclock?.gpu_max_mhz ?? 0;
    return mhz >= 1600 ? mhz : 1600;
  });

  const mountedRef = useRef<boolean>(true);
  const tvDraftDirtyRef = useRef<boolean>(false);
  const pendingSliderPatchRef = useRef<Record<string, unknown> | null>(null);
  const sliderDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const scalingSectionRef = useRef<HTMLDivElement | null>(null);
  const tvSectionRef = useRef<HTMLDivElement | null>(null);
  const overclockSectionRef = useRef<HTMLDivElement | null>(null);

  const markTvDraftDirty = () => {
    tvDraftDirtyRef.current = true;
    setTvDirty(true);
  };

  const syncProfileDrafts = useCallback((nextProf: DockProfile, forceTvDraft = false) => {
    setProfile(nextProf);
    setFsrDraft(nextProf.fsr_sharpness);
    setDockedTdpDraft(nextProf.docked_tdp_watts);
    setHandheldTdpDraft(nextProf.handheld_tdp_watts);
    if (forceTvDraft || !tvDraftDirtyRef.current) {
      setTvHostDraft(nextProf.tv?.host ?? "");
      const fallbackPort = DEFAULT_TV_PORTS[nextProf.tv?.driver ?? "cec"] ?? 8002;
      setTvPortDraft(String(nextProf.tv?.port ?? fallbackPort));
      setTvMacDraft(nextProf.tv?.mac_address ?? "");
      setTvWebhookDraft(nextProf.tv?.webhook_url ?? "");
      if (forceTvDraft) {
        tvDraftDirtyRef.current = false;
        setTvDirty(false);
      }
    }
    setBoostTdpDraft(nextProf.overclock?.boost_tdp_watts ?? 18);
    const nextGpu = nextProf.overclock?.gpu_max_mhz ?? 0;
    setGpuMaxDraft(nextGpu >= 1600 ? nextGpu : 1600);
  }, []);

  const refreshAll = useCallback(
    async (quiet = false) => {
      if (!quiet && mountedRef.current) {
        setBusy(true);
      }
      try {
        const [nextStatus, nextProfile] = await Promise.all([
          transport.getStatus(),
          transport.getActiveProfile(),
        ]);
        if (!mountedRef.current) return;
        setStatus(nextStatus);
        syncProfileDrafts(nextProfile);
      } catch (err) {
        if (!quiet && mountedRef.current) {
          setFeedback({
            tone: "crimson",
            text: `Failed refreshing status: ${err instanceof Error ? err.message : String(err)}`,
          });
        }
      } finally {
        if (mountedRef.current) {
          setLoading(false);
          if (!quiet) {
            setBusy(false);
          }
        }
      }
    },
    [syncProfileDrafts, transport],
  );

  useEffect(() => {
    mountedRef.current = true;
    if (!initialStatus || !initialProfile) {
      void refreshAll(false);
    }
    let pollTimer: ReturnType<typeof setInterval> | null = null;
    const onTransition = () => {
      void refreshAll(true);
    };
    if (!initialStatus && typeof window !== "undefined") {
      pollTimer = setInterval(() => {
        void refreshAll(true);
      }, 2500);
      window.addEventListener("switchdeck:transition", onTransition);
    }
    return () => {
      mountedRef.current = false;
      if (pollTimer) {
        clearInterval(pollTimer);
      }
      if (!initialStatus && typeof window !== "undefined") {
        window.removeEventListener("switchdeck:transition", onTransition);
      }
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
    async (
      patch: Record<string, unknown>,
      message?: string,
      options?: {
        setGlobalBusy?: boolean;
        target?: "global" | "tv" | "oc";
        forceTvSync?: boolean;
      },
    ) => {
      const shouldBusy = options?.setGlobalBusy ?? true;
      const target = options?.target ?? "global";
      const setTargetMsg = (msg: FeedbackMessage) => {
        if (target === "tv") setTvFeedback(msg);
        else if (target === "oc") setOcFeedback(msg);
        else setFeedback(msg);
      };
      if (shouldBusy && mountedRef.current) {
        setBusy(true);
      }
      try {
        const updated = await transport.updateProfile(patch);
        if (!mountedRef.current) return;
        syncProfileDrafts(updated, Boolean(options?.forceTvSync));
        const refreshed = await transport.getStatus();
        if (!mountedRef.current) return;
        setStatus(refreshed);
        if (message) {
          setTargetMsg({ tone: "accent", text: message });
        }
      } catch (err) {
        if (mountedRef.current) {
          setTargetMsg({
            tone: "crimson",
            text: err instanceof Error ? err.message : String(err),
          });
        }
      } finally {
        if (shouldBusy && mountedRef.current) {
          setBusy(false);
        }
      }
    },
    [syncProfileDrafts, transport],
  );

  const scheduleSliderPatch = useCallback(
    (patch: Record<string, unknown>) => {
      pendingSliderPatchRef.current = mergeProfilePatch(
        pendingSliderPatchRef.current || {},
        patch,
      );
      if (sliderDebounceRef.current) {
        clearTimeout(sliderDebounceRef.current);
      }
      sliderDebounceRef.current = setTimeout(() => {
        const toSend = pendingSliderPatchRef.current;
        pendingSliderPatchRef.current = null;
        if (toSend) {
          void commitProfilePatch(toSend, undefined, { setGlobalBusy: false });
        }
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
      if (!mountedRef.current) return;
      setStatus(next);
      setFeedback({
        tone: "accent",
        text: checked ? "Built-in Deck controls kept active" : "Smart P1 auto-handoff enabled",
      });
    } catch (err) {
      if (mountedRef.current) {
        setFeedback({ tone: "crimson", text: String(err) });
      }
    } finally {
      if (mountedRef.current) {
        setBusy(false);
      }
    }
  };

  const handleChargeOverrideToggle = async (checked: boolean) => {
    setBusy(true);
    try {
      const next = await transport.setChargeOverride(checked);
      if (!mountedRef.current) return;
      setStatus(next);
      setFeedback({
        tone: checked ? "accent" : "sage",
        text: checked ? "Travel Charge 100% active until undock" : "80% battery cap restored",
      });
    } catch (err) {
      if (mountedRef.current) {
        setFeedback({ tone: "crimson", text: String(err) });
      }
    } finally {
      if (mountedRef.current) {
        setBusy(false);
      }
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
        text: "Native SteamClient app override unavailable",
      });
      return;
    }
    const targetW = profile?.preferred_container_width ?? 1920;
    const targetH = profile?.preferred_container_height ?? 1080;
    const dockedNow = Boolean(status?.is_docked);
    const applied = await transport.applyNativeAppResolution(
      targetW,
      targetH,
      dockedNow,
      status?.active_app_id,
    );
    if (!mountedRef.current) return;
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
      if (!mountedRef.current) return;
      setFeedback({
        tone: res.ok ? "sage" : "crimson",
        text: res.ok
          ? "Sent display mode nudge to HDMI output"
          : "Display nudge returned false (no active Gamescope display)",
      });
    } catch (err) {
      if (mountedRef.current) {
        setFeedback({
          tone: "crimson",
          text: err instanceof Error ? err.message : String(err),
        });
      }
    } finally {
      if (mountedRef.current) {
        setBusy(false);
      }
    }
  };

  const handleRebindBuiltin = async () => {
    setBusy(true);
    try {
      const next = await transport.rebindBuiltin();
      if (!mountedRef.current) return;
      setStatus(next);
      setFeedback({
        tone: "sage",
        text: "Deck built-in controls restored",
      });
    } catch (err) {
      if (mountedRef.current) {
        setFeedback({ tone: "crimson", text: String(err) });
      }
    } finally {
      if (mountedRef.current) {
        setBusy(false);
      }
    }
  };

  const handleSaveTvSettings = async () => {
    if (!profile) return;
    const driverKind: TvDriverKind = profile.tv.driver ?? "cec";
    const tvPatch: Record<string, unknown> = {
      driver: driverKind,
      host: tvHostDraft.trim(),
      port: parsePortDraft(tvPortDraft, driverKind),
      mac_address: tvMacDraft.trim(),
      hdmi_input: profile.tv.hdmi_input || "HDMI2",
      webhook_url: tvWebhookDraft.trim(),
    };
    const cleanPsk = tvPskDraft.trim();
    if (driverKind === "sony_bravia" && cleanPsk) {
      tvPatch.psk = cleanPsk;
    }
    await commitProfilePatch({ tv: tvPatch }, "TV configuration saved", {
      target: "tv",
      forceTvSync: true,
    });
    if (mountedRef.current && driverKind === "sony_bravia" && cleanPsk) {
      setTvPskDraft("");
    }
  };

  const handlePairTv = async (trustNewCert: boolean) => {
    const driverKind: TvDriverKind = profile?.tv?.driver ?? "samsung_tizen";
    const cleanHost = tvHostDraft.trim();
    if (!cleanHost) {
      setTvFeedback({ tone: "crimson", text: "Enter TV IP/Hostname before pairing" });
      return;
    }
    const cleanPsk = tvPskDraft.trim();
    if (driverKind === "sony_bravia" && !cleanPsk && !profile?.tv_paired) {
      setTvFeedback({ tone: "crimson", text: "Enter Sony TV Pre-Shared Key (PSK)" });
      return;
    }

    setBusy(true);
    setPairingBusy(true);
    setCertMismatch(false);
    setTvFeedback({
      tone: "accent",
      text:
        driverKind === "sony_bravia"
          ? `Verifying Sony Bravia PSK on ${cleanHost}...`
          : `Pairing with ${cleanHost} — accept the prompt on your TV...`,
    });
    try {
      const targetPort = parsePortDraft(tvPortDraft, driverKind);
      const cleanMac = tvMacDraft.trim();
      const hdmiInput = profile?.tv?.hdmi_input || "HDMI2";
      const res = transport.pairTv
        ? await transport.pairTv({
            driver: driverKind,
            host: cleanHost,
            port: targetPort,
            mac: cleanMac,
            hdmiInput,
            psk: cleanPsk,
            trustNewCert,
          })
        : await transport.pairSamsungTv(cleanHost, targetPort, cleanMac, trustNewCert);

      if (!mountedRef.current) return;
      if (res.ok) {
        if (driverKind === "sony_bravia") {
          setTvPskDraft("");
        }
        tvDraftDirtyRef.current = false;
        setTvDirty(false);
        if (res.profile) {
          syncProfileDrafts(res.profile, true);
        } else {
          await refreshAll(true);
        }
        if (!mountedRef.current) return;
        let msg: string;
        if (driverKind === "lg_webos") {
          msg = `LG webOS TV paired (${cleanHost})`;
        } else if (driverKind === "sony_bravia") {
          msg = `Sony Bravia PSK verified (${cleanHost})`;
        } else {
          msg = res.token_saved
            ? `Samsung TV paired (${cleanHost})`
            : `Connected to ${cleanHost} — accept Allow prompt on TV`;
        }
        setTvFeedback({ tone: "sage", text: msg });
      } else {
        setCertMismatch(Boolean(res.cert_mismatch));
        setTvFeedback({
          tone: "crimson",
          text: res.error || "TV pairing failed",
        });
      }
    } catch (err) {
      if (mountedRef.current) {
        setTvFeedback({ tone: "crimson", text: String(err) });
      }
    } finally {
      if (mountedRef.current) {
        setPairingBusy(false);
        setBusy(false);
      }
    }
  };

  const handleTestTvWake = async () => {
    if (!profile) return;
    setBusy(true);
    try {
      const driverKind: TvDriverKind = profile.tv.driver ?? "cec";
      const tvPatch: Record<string, unknown> = {
        driver: driverKind,
        host: tvHostDraft.trim(),
        port: parsePortDraft(tvPortDraft, driverKind),
        mac_address: tvMacDraft.trim(),
        hdmi_input: profile.tv.hdmi_input || "HDMI2",
        webhook_url: tvWebhookDraft.trim(),
      };
      if (driverKind === "sony_bravia" && tvPskDraft.trim()) {
        tvPatch.psk = tvPskDraft.trim();
      }
      const updated = await transport.updateProfile({ tv: tvPatch });
      if (!mountedRef.current) return;
      if (driverKind === "sony_bravia" && tvPskDraft.trim()) {
        setTvPskDraft("");
      }
      syncProfileDrafts(updated, true);
      const res = await transport.testTvWake();
      if (!mountedRef.current) return;
      if (res.cert_mismatch) {
        setCertMismatch(true);
      }
      setTvFeedback({
        tone: res.ok ? "sage" : "crimson",
        text: res.ok
          ? "TV wake signal sent"
          : res.error || "TV wake failed — check TV power or network",
      });
    } catch (err) {
      if (mountedRef.current) {
        setTvFeedback({ tone: "crimson", text: String(err) });
      }
    } finally {
      if (mountedRef.current) {
        setBusy(false);
      }
    }
  };

  if (loading && !status) {
    return (
      <div style={qamStyles.root}>
        <PanelSection title="Status">
          <PanelSectionRow>
            <div style={qamStyles.helperNote("neutral")}>Loading SwitchDeck status...</div>
          </PanelSectionRow>
        </PanelSection>
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
      `Preset applied: ${preset.label}`,
      { target: "oc" },
    );
  };

  // Concise status strings
  const primaryExternal = status?.active_controllers[0];
  const controllerValue = primaryExternal
    ? `${primaryExternal.name}${status?.builtin_controller_bound ? " (+Deck)" : ""}`
    : status?.builtin_controller_bound
      ? "Steam Deck (Built-in)"
      : "No Active Gamepad";
  const displayName = status?.is_docked
    ? profile?.display_name || status.active_connector || "External Display"
    : "Built-in Display";
  const powerParts: string[] = [
    `${status?.tdp_watts ?? "--"}W${status?.overclock_active ? " OC" : ""}`,
    status && status.charge_limit > 0 ? `${status.charge_limit}% Cap` : "100% Cap",
  ];
  if (status?.apu_temp_c != null) {
    powerParts.push(`${status.apu_temp_c.toFixed(0)}°C`);
  }
  if (status?.deck_model === "Jupiter" && status.lcd_bluetooth_wakeup_enabled) {
    powerParts.push("BT Wake");
  }

  const hasAlerts = Boolean(
    status &&
      (status.unhandled_dongles.length > 0 ||
        status.last_error ||
        status.overclock_thermal_throttled),
  );

  let ocSummaryLine = `Stock <= 15W`;
  let ocSummaryTone: "neutral" | "ochre" | "crimson" = "neutral";
  if (status?.overclock_thermal_throttled) {
    ocSummaryLine = "Thermal step-down <= 15W (APU >= 90°C)";
    ocSummaryTone = "crimson";
  } else if (status?.overclock_active) {
    ocSummaryLine =
      status.overclock_status_note ||
      `Active: ${boostTdpDraft}W · ${gpuMaxDraft <= 1600 ? "GPU Auto" : `${gpuMaxDraft} MHz`}`;
    ocSummaryTone = "ochre";
  } else if (oc.enabled && !status?.is_docked) {
    ocSummaryLine = "Armed (applies when docked on AC)";
  } else if (oc.enabled && !status?.ac_online) {
    ocSummaryLine = "Blocked: connect AC power";
    ocSummaryTone = "crimson";
  }
  if (status?.apu_temp_c != null) {
    ocSummaryLine = `${ocSummaryLine} · ${status.apu_temp_c.toFixed(0)}°C`;
  }

  return (
    <div style={qamStyles.root}>
      {status && (
        <PanelSection title={status.is_docked ? "Status · Docked" : "Status · Handheld"}>
          <StatusRow label="Display" value={`${displayName} · ${formatModeLabel(status)}`} />
          <StatusRow label="Controller" value={controllerValue} />
          <StatusRow label="Audio" value={status.audio_sink || "System Default"} />
          <StatusRow label="Scaling" value={formatScalingSummary(status)} />
          <StatusRow label="Power" value={powerParts.join(" · ")} />
        </PanelSection>
      )}

      {hasAlerts && status && (
        <PanelSection title="Alerts">
          {status.overclock_thermal_throttled && (
            <PanelSectionRow>
              <div style={qamStyles.helperNote("ochre")}>
                Thermal Watchdog Active (&lt;= 15W): APU reached &gt;= 90°C and stepped down
                until cooling below 80°C.
              </div>
            </PanelSectionRow>
          )}
          {status.unhandled_dongles.map((dongle) => (
            <PanelSectionRow key={`${dongle.usb_id}-${dongle.sysfs_path}`}>
              <div style={qamStyles.helperNote("crimson")}>
                <strong>[{dongle.usb_id}] {dongle.device_name}:</strong> {dongle.remediation}
              </div>
            </PanelSectionRow>
          ))}
          {status.last_error && (
            <PanelSectionRow>
              <div style={qamStyles.helperNote("crimson")}>{status.last_error}</div>
            </PanelSectionRow>
          )}
        </PanelSection>
      )}

      {feedback && (
        <div style={qamStyles.helperNote(feedback.tone)} role="status">
          {feedback.text}
        </div>
      )}

      <PanelSection title="Quick Controls">
        <PanelSectionRow>
          <ToggleField
            label="Keep Built-in Controls"
            description="Keep Steam Deck inputs active with external P1"
            checked={Boolean(status?.manual_keep_builtin)}
            disabled={busy}
            onChange={(val) => void handleKeepBuiltinToggle(val)}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <ToggleField
            label="Travel Charge 100%"
            description="Override 80% dock battery cap until undock"
            checked={Boolean(status?.travel_charge_override)}
            disabled={busy}
            onChange={(val) => void handleChargeOverrideToggle(val)}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <ToggleField
            label="Transition Notification"
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
                ? `Set running app override to ${profile?.preferred_container_width ?? 1920}x${profile?.preferred_container_height ?? 1080}`
                : "Reset running app override"
            }
            onClick={() => void handleAutoNativeAppRes()}
          >
            Sync Game Resolution
          </ButtonItem>
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={busy} onClick={() => void handleNudgeDisplay()}>
            Fix Blank TV / Nudge HDMI
          </ButtonItem>
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={busy} onClick={() => void handleRebindBuiltin()}>
            Rebind Deck Controls
          </ButtonItem>
        </PanelSectionRow>
      </PanelSection>

      {profile && (
        <>
          <div ref={scalingSectionRef}>
            <PanelSection title="Display & Power">
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
                  description="Lower resolution if GPU load >= 97%"
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
                  onChange={(val) => {
                    setHandheldTdpDraft(val);
                    scheduleSliderPatch({ handheld_tdp_watts: val });
                  }}
                />
              </PanelSectionRow>
              <PanelSectionRow>
                <ToggleField
                  label="Pause on Undock"
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
                    const defaultPort = DEFAULT_TV_PORTS[nextDriver] ?? 8002;
                    setCertMismatch(false);
                    setTvFeedback(null);
                    setTvPskDraft("");
                    setTvPortDraft(String(defaultPort));
                    void commitProfilePatch(
                      {
                        tv: {
                          driver: nextDriver,
                          port: defaultPort,
                        },
                      },
                      `TV driver set to ${opt.label}`,
                      { target: "tv", forceTvSync: true },
                    );
                  }}
                />
              </PanelSectionRow>

              {(activeDriver === "samsung_tizen" ||
                activeDriver === "lg_webos" ||
                activeDriver === "sony_bravia" ||
                activeDriver === "roku_ecp" ||
                activeDriver === "wol") && (
                <>
                  <PanelSectionRow>
                    <TextField
                      label={activeDriver === "wol" ? "Broadcast IP" : "TV Host / IP"}
                      placeholder={activeDriver === "wol" ? "255.255.255.255" : "192.168.1.50"}
                      value={tvHostDraft}
                      disabled={busy}
                      onChange={(e) => {
                        markTvDraftDirty();
                        setTvHostDraft(e.target.value);
                      }}
                    />
                  </PanelSectionRow>
                  <PanelSectionRow>
                    <TextField
                      label="TV Port"
                      placeholder={String(DEFAULT_TV_PORTS[activeDriver] ?? 8002)}
                      value={tvPortDraft}
                      disabled={busy}
                      onChange={(e) => {
                        markTvDraftDirty();
                        setTvPortDraft(e.target.value);
                      }}
                    />
                  </PanelSectionRow>
                  <PanelSectionRow>
                    <TextField
                      label="TV MAC (WoL)"
                      placeholder="AA:BB:CC:DD:EE:FF"
                      value={tvMacDraft}
                      disabled={busy}
                      onChange={(e) => {
                        markTvDraftDirty();
                        setTvMacDraft(e.target.value);
                      }}
                    />
                  </PanelSectionRow>
                </>
              )}

              {(activeDriver === "lg_webos" ||
                activeDriver === "sony_bravia" ||
                activeDriver === "roku_ecp" ||
                activeDriver === "webhook") && (
                <PanelSectionRow>
                  <DropdownItem
                    label="HDMI Input"
                    rgOptions={HDMI_INPUT_OPTIONS}
                    selectedOption={profile.tv.hdmi_input || "HDMI2"}
                    disabled={busy}
                    onChange={(opt) => {
                      const nextInput = String(opt.data || "HDMI2");
                      void commitProfilePatch(
                        { tv: { hdmi_input: nextInput } },
                        `TV input set to ${opt.label}`,
                        { target: "tv" },
                      );
                    }}
                  />
                </PanelSectionRow>
              )}

              {activeDriver === "sony_bravia" && (
                <PanelSectionRow>
                  <TextField
                    label="Pre-Shared Key"
                    bIsPassword
                    placeholder={profile.tv_paired ? "Saved (enter new PSK)" : "TV PSK"}
                    value={tvPskDraft}
                    disabled={busy}
                    onChange={(e) => {
                      markTvDraftDirty();
                      setTvPskDraft(e.target.value);
                    }}
                  />
                </PanelSectionRow>
              )}

              {activeDriver === "webhook" && (
                <PanelSectionRow>
                  <TextField
                    label="Webhook URL"
                    placeholder="http://homeassistant.local:8123/api/webhook/switchdeck"
                    value={tvWebhookDraft}
                    disabled={busy}
                    onChange={(e) => {
                      markTvDraftDirty();
                      setTvWebhookDraft(e.target.value);
                    }}
                  />
                </PanelSectionRow>
              )}

              {(activeDriver === "samsung_tizen" || activeDriver === "lg_webos") &&
                (hasCertPin || profile.tv_paired) && (
                  <PanelSectionRow>
                    <div style={qamStyles.helperNote("sage")}>
                      {profile.tv_paired ? "Paired" : "Connected"}
                      {profile.tv_cert_fingerprint ? (
                        <span style={qamStyles.monoSubtle}>
                          {" "}
                          · sha256: {shortFingerprint(profile.tv_cert_fingerprint)}
                        </span>
                      ) : null}
                    </div>
                  </PanelSectionRow>
                )}

              {activeDriver === "sony_bravia" && profile.tv_paired && (
                <PanelSectionRow>
                  <div style={qamStyles.helperNote("sage")}>Pre-Shared Key saved</div>
                </PanelSectionRow>
              )}

              {certMismatch &&
                (activeDriver === "samsung_tizen" || activeDriver === "lg_webos") && (
                  <PanelSectionRow>
                    <ButtonItem
                      layout="below"
                      disabled={busy}
                      onClick={() => void handlePairTv(true)}
                    >
                      Trust New TV Cert &amp; Re-Pair
                    </ButtonItem>
                  </PanelSectionRow>
                )}

              {(activeDriver === "samsung_tizen" ||
                activeDriver === "lg_webos" ||
                activeDriver === "sony_bravia") && (
                <PanelSectionRow>
                  <ButtonItem
                    layout="below"
                    disabled={busy || pairingBusy}
                    onClick={() => void handlePairTv(false)}
                  >
                    {pairingBusy
                      ? "Pairing — Accept Prompt on TV..."
                      : activeDriver === "lg_webos"
                        ? "Pair LG webOS TV"
                        : activeDriver === "sony_bravia"
                          ? "Save & Verify Sony PSK"
                          : "Pair Samsung TV"}
                  </ButtonItem>
                </PanelSectionRow>
              )}

              {(tvDirty || Boolean(tvPskDraft.trim())) &&
                activeDriver !== "none" &&
                activeDriver !== "cec" && (
                  <PanelSectionRow>
                    <ButtonItem
                      layout="below"
                      disabled={busy || pairingBusy}
                      onClick={() => void handleSaveTvSettings()}
                    >
                      Save TV Settings
                    </ButtonItem>
                  </PanelSectionRow>
                )}

              {activeDriver !== "none" && (
                <PanelSectionRow>
                  <ButtonItem
                    layout="below"
                    disabled={busy || pairingBusy}
                    onClick={() => void handleTestTvWake()}
                  >
                    Test TV Wake
                  </ButtonItem>
                </PanelSectionRow>
              )}

              {tvFeedback && (
                <PanelSectionRow>
                  <div style={qamStyles.helperNote(tvFeedback.tone)} role="status">
                    {tvFeedback.text}
                  </div>
                </PanelSectionRow>
              )}
            </PanelSection>
          </div>

          <div ref={overclockSectionRef}>
            <PanelSection title="Docked Overclock (Experimental)">
              {!oc.risk_acknowledged ? (
                <>
                  <PanelSectionRow>
                    <div style={qamStyles.helperNote("neutral")}>
                      Volatile sysfs overclock (up to 22W TDP / 2000 MHz GPU, no undervolting or
                      BIOS edits). Requires AC power and resets on undock or &gt;= 90°C.
                    </div>
                  </PanelSectionRow>
                  <PanelSectionRow>
                    <ButtonItem
                      layout="below"
                      disabled={busy}
                      onClick={() =>
                        void commitProfilePatch(
                          { overclock: { risk_acknowledged: true } },
                          "Docked overclock unlocked (off until enabled)",
                          { target: "oc" },
                        )
                      }
                    >
                      Unlock Experimental Controls
                    </ButtonItem>
                  </PanelSectionRow>
                  {ocFeedback && (
                    <PanelSectionRow>
                      <div style={qamStyles.helperNote(ocFeedback.tone)} role="status">
                        {ocFeedback.text}
                      </div>
                    </PanelSectionRow>
                  )}
                </>
              ) : (
                <>
                  <PanelSectionRow>
                    <div style={qamStyles.helperNote(ocSummaryTone)}>{ocSummaryLine}</div>
                  </PanelSectionRow>

                  {ocFeedback && (
                    <PanelSectionRow>
                      <div style={qamStyles.helperNote(ocFeedback.tone)} role="status">
                        {ocFeedback.text}
                      </div>
                    </PanelSectionRow>
                  )}

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
                      label="Enable Overclock"
                      checked={oc.enabled}
                      disabled={busy}
                      onChange={(val) =>
                        void commitProfilePatch(
                          { overclock: { enabled: val } },
                          val
                            ? status?.is_docked && status.ac_online
                              ? "Docked overclock active"
                              : "Overclock armed (waiting for dock + AC)"
                            : "Overclock disabled (<= 15W stock)",
                          { target: "oc" },
                        )
                      }
                    />
                  </PanelSectionRow>

                  <PanelSectionRow>
                    <SliderField
                      label="Boost TDP"
                      value={boostTdpDraft}
                      min={15}
                      max={22}
                      step={1}
                      valueSuffix="W"
                      showValue
                      onChange={(val) => {
                        setBoostTdpDraft(val);
                        scheduleSliderPatch({ overclock: { boost_tdp_watts: val } });
                      }}
                    />
                  </PanelSectionRow>

                  <PanelSectionRow>
                    <SliderField
                      label={gpuMaxDraft <= 1600 ? "Max GPU (Auto)" : "Max GPU Clock"}
                      value={gpuMaxDraft}
                      min={1600}
                      max={2000}
                      step={50}
                      valueSuffix=" MHz"
                      showValue
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
                      label="CPU Turbo Boost"
                      description="Turn off in GPU-bound games for extra GPU power headroom"
                      checked={oc.cpu_boost}
                      disabled={busy}
                      onChange={(val) =>
                        void commitProfilePatch(
                          { overclock: { cpu_boost: val } },
                          val ? "CPU turbo boost enabled" : "CPU turbo boost disabled",
                          { target: "oc" },
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
                          "Overclock reset to stock 15W and locked",
                          { target: "oc" },
                        );
                      }}
                    >
                      Reset &amp; Lock
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
