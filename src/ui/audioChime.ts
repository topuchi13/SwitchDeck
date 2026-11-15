export const CHIME_PREF_STORAGE_KEY = "switchdeck.chimeEnabled";

let sharedAudioCtx: AudioContext | null = null;

function getAudioContext(): AudioContext | null {
  if (typeof window === "undefined") {
    return null;
  }
  const win = window as unknown as {
    AudioContext?: typeof AudioContext;
    webkitAudioContext?: typeof AudioContext;
  };
  const Ctor = win.AudioContext ?? win.webkitAudioContext;
  if (!Ctor) {
    return null;
  }
  try {
    if (!sharedAudioCtx || sharedAudioCtx.state === "closed") {
      sharedAudioCtx = new Ctor();
    }
    if (sharedAudioCtx.state === "suspended") {
      void sharedAudioCtx.resume().catch(() => undefined);
    }
    return sharedAudioCtx;
  } catch {
    return null;
  }
}

export function isChimeAndToastEnabled(): boolean {
  try {
    if (typeof window === "undefined" || !window.localStorage) {
      return true;
    }
    const raw = window.localStorage.getItem(CHIME_PREF_STORAGE_KEY);
    return raw === null ? true : raw === "true";
  } catch {
    return true;
  }
}

export function setChimeAndToastEnabled(enabled: boolean): void {
  try {
    if (typeof window !== "undefined" && window.localStorage) {
      window.localStorage.setItem(CHIME_PREF_STORAGE_KEY, enabled ? "true" : "false");
    }
  } catch {
    // Ignore storage errors in restricted contexts
  }
}

/**
 * Synthesize the mechanical two-tone Nintendo Switch "Click-Clack" rail chime:
 * Phase 1 (12ms subtle mechanical click) + Phase 2 (65ms crisp resonant snap).
 * Safe no-op if WebAudio AudioContext is unavailable or blocked.
 */
export function playSwitchClickClack(kind: "docked" | "undocked" = "docked"): void {
  const ctx = getAudioContext();
  if (!ctx) {
    return;
  }

  try {
    const now = ctx.currentTime + 0.005;

    // Phase 1: 12ms subtle tactile slide-click
    const clickOsc = ctx.createOscillator();
    const clickGain = ctx.createGain();
    clickOsc.type = "triangle";
    const clickStartHz = kind === "docked" ? 1320 : 1080;
    const clickEndHz = kind === "docked" ? 940 : 760;
    clickOsc.frequency.setValueAtTime(clickStartHz, now);
    clickOsc.frequency.exponentialRampToValueAtTime(clickEndHz, now + 0.012);

    clickGain.gain.setValueAtTime(0.001, now);
    clickGain.gain.linearRampToValueAtTime(0.14, now + 0.002);
    clickGain.gain.exponentialRampToValueAtTime(0.0008, now + 0.014);

    clickOsc.connect(clickGain);
    clickGain.connect(ctx.destination);
    clickOsc.start(now);
    clickOsc.stop(now + 0.016);

    // Phase 2: 65ms crisp resonant lock snap ("clack")
    const snapTime = now + 0.058;
    const bodyOsc = ctx.createOscillator();
    const harmonicOsc = ctx.createOscillator();
    const snapGain = ctx.createGain();
    const harmonicGain = ctx.createGain();

    bodyOsc.type = "sine";
    harmonicOsc.type = "triangle";

    const baseHz = kind === "docked" ? 1760 : 1480;
    const harmonicHz = kind === "docked" ? 2640 : 2220;
    bodyOsc.frequency.setValueAtTime(baseHz, snapTime);
    bodyOsc.frequency.exponentialRampToValueAtTime(baseHz * 0.88, snapTime + 0.065);

    harmonicOsc.frequency.setValueAtTime(harmonicHz, snapTime);
    harmonicOsc.frequency.exponentialRampToValueAtTime(harmonicHz * 0.92, snapTime + 0.045);

    snapGain.gain.setValueAtTime(0.001, snapTime);
    snapGain.gain.linearRampToValueAtTime(0.18, snapTime + 0.003);
    snapGain.gain.exponentialRampToValueAtTime(0.0008, snapTime + 0.068);

    harmonicGain.gain.setValueAtTime(0.001, snapTime);
    harmonicGain.gain.linearRampToValueAtTime(0.075, snapTime + 0.002);
    harmonicGain.gain.exponentialRampToValueAtTime(0.0008, snapTime + 0.048);

    bodyOsc.connect(snapGain);
    harmonicOsc.connect(harmonicGain);
    snapGain.connect(ctx.destination);
    harmonicGain.connect(ctx.destination);

    bodyOsc.start(snapTime);
    harmonicOsc.start(snapTime);
    bodyOsc.stop(snapTime + 0.072);
    harmonicOsc.stop(snapTime + 0.052);
  } catch {
    // Safe no-op if audio graph fails
  }
}
