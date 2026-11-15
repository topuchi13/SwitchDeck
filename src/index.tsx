import {
  addEventListener,
  callable,
  definePlugin,
  removeEventListener,
  toaster,
} from "@decky/api";
import { isChimeAndToastEnabled, playSwitchClickClack } from "./ui/audioChime";
import { QuickAccessPanel } from "./ui/QuickAccessPanel";
import { SwitchJoyConIcon, SwitchToastCard } from "./ui/SwitchToast";
import type {
  DaemonStatus,
  DockProfile,
  PairSamsungResult,
  PairTvParams,
  PairTvResult,
  SwitchDeckTransport,
  TransitionPayload,
} from "./ui/types";

interface SteamClientGlobal {
  Apps?: {
    SetAppResolutionOverride?: (appId: number, resolution: string) => void;
    GetActiveAppID?: () => number;
  };
  UI?: {
    GetFocusedWindowAppID?: () => number;
  };
}

const getStatusRpc = callable<[], DaemonStatus>("get_status");
const getActiveProfileRpc = callable<[], DockProfile>("get_active_profile");
const updateProfileRpc = callable<[Record<string, unknown>], DockProfile>("update_profile");
const setKeepBuiltinRpc = callable<[boolean], DaemonStatus>("set_keep_builtin");
const rebindBuiltinRpc = callable<[], DaemonStatus>("rebind_builtin");
const setChargeOverrideRpc = callable<[boolean], DaemonStatus>("set_charge_override");
const nudgeDisplayRpc = callable<[], { ok: boolean }>("nudge_display");
const pairSamsungTvRpc = callable<[string, number, string, boolean], PairSamsungResult>(
  "pair_samsung_tv",
);
const pairTvRpc = callable<[string, string, number, string, string, string, boolean], PairTvResult>(
  "pair_tv",
);
const testTvWakeRpc = callable<[], { ok: boolean }>("test_tv_wake");

async function applyNativeAppResolution(
  width: number,
  height: number,
  docked: boolean,
): Promise<boolean> {
  try {
    const win = window as unknown as {
      SteamClient?: SteamClientGlobal;
      Router?: { MainRunningApp?: { appid?: number } };
    };
    const apps = win.SteamClient?.Apps;
    if (!apps || typeof apps.SetAppResolutionOverride !== "function") {
      return false;
    }
    const appId =
      win.Router?.MainRunningApp?.appid ??
      apps.GetActiveAppID?.() ??
      win.SteamClient?.UI?.GetFocusedWindowAppID?.();
    if (!appId || appId <= 0) {
      return false;
    }
    const resolution = docked ? `${width}x${height}` : "Default";
    apps.SetAppResolutionOverride(appId, resolution);
    return true;
  } catch {
    return false;
  }
}

const transport: SwitchDeckTransport = {
  getStatus: () => getStatusRpc(),
  getActiveProfile: () => getActiveProfileRpc(),
  updateProfile: (patch) => updateProfileRpc(patch),
  setKeepBuiltin: (enabled) => setKeepBuiltinRpc(enabled),
  rebindBuiltin: () => rebindBuiltinRpc(),
  setChargeOverride: (enabled) => setChargeOverrideRpc(enabled),
  nudgeDisplay: () => nudgeDisplayRpc(),
  pairSamsungTv: (host, port = 8002, mac = "", trustNewCert = false) =>
    pairSamsungTvRpc(host, port, mac, trustNewCert),
  pairTv: ({
    driver,
    host,
    port = 0,
    mac = "",
    hdmiInput = "",
    psk = "",
    trustNewCert = false,
  }: PairTvParams) => pairTvRpc(driver, host, port, mac, hdmiInput, psk, trustNewCert),
  testTvWake: () => testTvWakeRpc(),
  applyNativeAppResolution,
};

export default definePlugin(() => {
  const handleTransition = (payload: TransitionPayload) => {
    if (!payload || !isChimeAndToastEnabled()) {
      return;
    }
    playSwitchClickClack(payload.kind);
    toaster.toast({
      title: payload.kind === "docked" ? "SwitchDeck · Docked" : "SwitchDeck · Handheld",
      body: <SwitchToastCard transition={payload} compact />,
      icon: <SwitchJoyConIcon size={22} />,
      duration: 4200,
      playSound: false,
      showToast: true,
    });
  };

  const listener = addEventListener<[TransitionPayload]>(
    "switchdeck_transition",
    handleTransition,
  );

  return {
    name: "SwitchDeck",
    titleView: (
      <div style={{ display: "flex", alignItems: "center", gap: "8px", fontWeight: 700 }}>
        <SwitchJoyConIcon size={18} />
        <span>SwitchDeck</span>
      </div>
    ),
    content: <QuickAccessPanel transport={transport} />,
    icon: <SwitchJoyConIcon size={18} />,
    onDismount() {
      removeEventListener("switchdeck_transition", listener);
    },
  };
});
