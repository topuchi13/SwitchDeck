"""Deterministic SwitchDeck state machine & dock/undock orchestrator."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import replace
from typing import Any

from .backends.protocol import HardwareBackend
from .domain import DaemonStatus, DeckModel, DisplayConnector, DisplayMode, ScalingDecision, DockProfile
from .edid import select_best_output_mode
from .profiles import ProfileStore
from .scaling import compute_universal_scaling
from .tv import create_tv_driver

LOG = logging.getLogger("switchdeck.coordinator")
MAX_HOLD_PAUSE_SEC = 15.0


class SwitchDeckCoordinator:
    """Reconciles hardware snapshots into Switch-like dock/handheld transitions."""

    def __init__(
        self,
        backend: HardwareBackend,
        store: ProfileStore | None = None,
        hold_pause_on_undock: bool = False,
    ) -> None:
        self.backend = backend
        self.store = store or ProfileStore()
        self.hold_pause_on_undock = hold_pause_on_undock
        self._lock = threading.RLock()

        self.is_docked: bool | None = None
        self.active_edid_id: str | None = None
        self.manual_keep_builtin: bool = False
        self.travel_charge_override: bool = False
        self.paused_pid: int | None = None
        self._paused_at: float | None = None

        self._consecutive_gpu_overload: int = 0
        self._last_scaling: ScalingDecision | None = None
        self._last_scaling_key: tuple[int, int, int, int, int, bool] | None = None
        self._keepalive_initialized: bool = False

        self._transition_seq: int = 0
        self._last_transition: dict[str, Any] | None = None
        self._last_error: str | None = None

    def _pick_primary_connector(self, displays: list[DisplayConnector]) -> DisplayConnector | None:
        connected = [d for d in displays if d.connected]
        return connected[0] if connected else None

    def _handle_audio_transition(
        self,
        docked_now: bool,
        prev_edid_id: str | None,
        new_edid_id: str | None,
        display_name: str,
    ) -> str | None:
        if not self._keepalive_initialized:
            self.backend.ensure_wireplumber_keepalive()
            self._keepalive_initialized = True

        audio = self.backend.get_audio_state()
        current_kind = audio.default_sink.kind if audio.default_sink else "other"

        if self.is_docked is None or self.is_docked == docked_now:
            return audio.default_sink.description if audio.default_sink else None

        handheld_prof = self.store.get_handheld_profile()
        if docked_now:
            # Save handheld speaker volume before moving to HDMI
            if current_kind == "speakers":
                handheld_prof.handheld_volume = audio.volume
                self.store.put_profile(handheld_prof)

            dock_prof = self.store.get_profile(new_edid_id, display_name)
            # Switch parity: if wireless Bluetooth headphones are active, keep them!
            if current_kind != "bluetooth":
                hdmi_sink = next((s for s in audio.sinks if s.kind == "hdmi"), None)
                if hdmi_sink is not None:
                    self.backend.set_default_audio_sink(hdmi_sink.sink_id)
                    self.backend.set_sink_volume(dock_prof.docked_volume)
        else:
            # Save docked HDMI volume before moving back to built-in speakers
            if current_kind == "hdmi":
                prev_prof = self.store.get_profile(prev_edid_id)
                prev_prof.docked_volume = audio.volume
                self.store.put_profile(prev_prof)

            if current_kind != "bluetooth":
                speaker_sink = next((s for s in audio.sinks if s.kind == "speakers"), None)
                if speaker_sink is not None:
                    self.backend.set_default_audio_sink(speaker_sink.sink_id)
                    self.backend.set_sink_volume(handheld_prof.handheld_volume)

        updated_audio = self.backend.get_audio_state()
        return updated_audio.default_sink.description if updated_audio.default_sink else None

    def _dispatch_tv_wake_async(self, prof: DockProfile) -> None:
        driver = create_tv_driver(
            prof.tv.driver,
            cec_trigger=self.backend.trigger_hdmi_cec_wake,
            get_token=self.store.get_token,
            set_token=self.store.set_token,
            get_cert_fingerprint=self.store.get_cert_fingerprint,
            set_cert_fingerprint=self.store.set_cert_fingerprint,
        )
        if driver is None:
            return
        tv_cfg = replace(prof.tv)

        def _tv_worker() -> None:
            try:
                driver.wake_and_switch(tv_cfg)
            except Exception as exc:
                LOG.warning("Background TV wake/switch failed: %s", exc)
                with self._lock:
                    self._last_error = f"TV wake failed: {exc}"

        threading.Thread(target=_tv_worker, name="switchdeck-tv-wake", daemon=True).start()

    def _apply_power_and_tv(
        self,
        docked_now: bool,
        ac_online: bool,
        edid_id: str | None,
        display_name: str,
        is_transition: bool,
    ) -> None:
        if docked_now:
            prof = self.store.get_profile(edid_id, display_name)
            if is_transition:
                if ac_online:
                    self.backend.set_tdp_limit(prof.docked_tdp_watts)
                    self.backend.set_gpu_performance_auto()
                target_cap = -1 if self.travel_charge_override else prof.docked_charge_limit
                self.backend.set_charge_limit(target_cap)
                self._dispatch_tv_wake_async(prof)
        else:
            if is_transition:
                handheld_prof = self.store.get_handheld_profile()
                self.travel_charge_override = False
                self.backend.set_tdp_limit(handheld_prof.handheld_tdp_watts)
                self.backend.set_charge_limit(-1)

    def _apply_scaling(
        self,
        docked_now: bool,
        conn: DisplayConnector | None,
        best_mode: DisplayMode | None,
        edid_id: str | None,
        display_name: str,
        is_transition: bool,
    ) -> ScalingDecision:
        prof = self.store.get_profile(edid_id, display_name) if docked_now else self.store.get_handheld_profile()
        game = self.backend.get_active_game_window()

        if (
            docked_now
            and game is not None
            and game.height >= 900
            and game.gpu_busy_percent is not None
            and game.gpu_busy_percent >= 97
        ):
            self._consecutive_gpu_overload += 1
        else:
            self._consecutive_gpu_overload = 0

        decision = compute_universal_scaling(
            is_docked=docked_now,
            output_mode=best_mode,
            game=game,
            profile=prof,
            consecutive_gpu_overload=self._consecutive_gpu_overload,
            vrr_capable=(conn.vrr_capable if conn else False),
        )
        key = (
            decision.target_width,
            decision.target_height,
            int(decision.scaling_filter),
            int(decision.scaling_scaler),
            decision.fsr_sharpness,
            decision.enable_vrr,
        )
        if is_transition or key != self._last_scaling_key:
            server_idx = game.server_idx if game is not None else 1
            self.backend.apply_gamescope_scaling(decision, server_idx=server_idx)
            self._last_scaling_key = key
        self._last_scaling = decision
        return decision

    def _record_transition_if_needed(
        self,
        prev_docked: bool | None,
        prev_edid: str | None,
        docked_now: bool,
        edid_id: str | None,
        display_name: str,
        best_mode: DisplayMode | None,
        scaling_decision: ScalingDecision,
        builtin_bound: bool,
        active_ctrls: list,
        tdp_watts: int,
        charge_limit: int,
        audio_desc: str | None,
    ) -> None:
        if prev_docked is None:
            return
        if prev_docked == docked_now and (not docked_now or prev_edid == edid_id):
            return
        self._transition_seq += 1
        p1_controller = active_ctrls[0].name if (not builtin_bound and active_ctrls) else "Steam Deck"
        self._last_transition = {
            "seq": self._transition_seq,
            "kind": "docked" if docked_now else "undocked",
            "display_name": display_name,
            "output_mode": best_mode.label if best_mode is not None else "1280x800",
            "vrr_enabled": bool(scaling_decision.enable_vrr),
            "p1_controller": p1_controller,
            "scaling_summary": (
                f"{scaling_decision.target_width}x{scaling_decision.target_height} "
                f"{scaling_decision.scaling_filter.name}"
            ),
            "tdp_watts": tdp_watts,
            "charge_limit": charge_limit,
            "audio_sink": audio_desc,
        }

    def reconcile(self) -> DaemonStatus:
        """Observe hardware state and execute any required Switch-style transitions."""
        with self._lock:
            if (
                self.paused_pid is not None
                and self._paused_at is not None
                and (time.monotonic() - self._paused_at) >= MAX_HOLD_PAUSE_SEC
            ):
                LOG.warning(
                    "Watchdog auto-resuming held game pid=%s after %.1fs",
                    self.paused_pid,
                    MAX_HOLD_PAUSE_SEC,
                )
                self.resume_paused_game()

            prev_docked = self.is_docked
            prev_edid = self.active_edid_id

            deck_model = self.backend.get_deck_model()
            ac_online = self.backend.is_ac_online()
            displays = self.backend.get_external_displays()
            primary_conn = self._pick_primary_connector(displays)
            docked_now = primary_conn is not None

            edid_id = (
                primary_conn.edid.profile_id
                if (primary_conn and primary_conn.edid)
                else ("default" if docked_now else None)
            )
            display_name = (
                primary_conn.edid.monitor_name
                if (primary_conn and primary_conn.edid)
                else (primary_conn.name if primary_conn else "Handheld")
            )
            best_mode = select_best_output_mode(primary_conn.modes) if primary_conn else None
            is_transition = (prev_docked is None) or (prev_docked != docked_now) or (
                docked_now and prev_edid != edid_id
            )
            did_real_transition = prev_docked is not None and (
                prev_docked != docked_now or (docked_now and prev_edid != edid_id)
            )
            if did_real_transition:
                self._last_error = None

            if prev_docked is True and not docked_now:
                self.manual_keep_builtin = False

            # Optional mid-game undock pause while inputs & display settle
            transient_pause_pid: int | None = None
            if prev_docked is True and not docked_now:
                handheld_prof = self.store.get_handheld_profile()
                active_game = self.backend.get_active_game_window()
                if handheld_prof.auto_pause_on_undock and active_game and active_game.pid:
                    if self.backend.pause_game_process(active_game.pid):
                        transient_pause_pid = active_game.pid
                        if self.hold_pause_on_undock:
                            self.paused_pid = active_game.pid
                            self._paused_at = time.monotonic()

            try:
                # 1. Smart Player 1 controller handoff (dock-gated + active-input aware)
                all_controllers = self.backend.get_external_controllers()
                active_ctrls = [c for c in all_controllers if c.is_actively_awake]
                sleeping_ctrls = [c for c in all_controllers if not c.is_actively_awake]
                should_unbind_builtin = (
                    docked_now and len(active_ctrls) >= 1 and not self.manual_keep_builtin
                )
                self.backend.set_builtin_controller_bound(not should_unbind_builtin)

                # 2. Model-aware LCD (Jupiter) Bluetooth/USB wakeup gating
                if deck_model == DeckModel.JUPITER_LCD:
                    self.backend.set_lcd_bluetooth_wakeup(docked_now)

                # 3. Audio routing + split handheld/docked volume memory
                audio_desc = self._handle_audio_transition(
                    docked_now=docked_now,
                    prev_edid_id=prev_edid,
                    new_edid_id=edid_id,
                    display_name=display_name,
                )

                # 4. Power profiles, battery longevity cap & TV power/input control
                self._apply_power_and_tv(
                    docked_now=docked_now,
                    ac_online=ac_online,
                    edid_id=edid_id,
                    display_name=display_name,
                    is_transition=is_transition,
                )

                # 5. Universal Gamescope resolution + FSR/PIXEL scaling
                scaling_decision = self._apply_scaling(
                    docked_now=docked_now,
                    conn=primary_conn,
                    best_mode=best_mode,
                    edid_id=edid_id,
                    display_name=display_name,
                    is_transition=is_transition,
                )
            except Exception as exc:
                self._last_error = str(exc)
                if transient_pause_pid is not None and self.paused_pid == transient_pause_pid:
                    self.resume_paused_game()
                raise
            finally:
                # Resume transient pause automatically unless an interactive overlay holds it
                if transient_pause_pid is not None and not self.hold_pause_on_undock:
                    self.backend.resume_game_process(transient_pause_pid)

            self.is_docked = docked_now
            self.active_edid_id = edid_id if docked_now else None

            prof = (
                self.store.get_profile(edid_id, display_name)
                if docked_now
                else self.store.get_handheld_profile()
            )
            builtin_bound = self.backend.is_builtin_controller_bound()
            charge_limit = self.backend.get_charge_limit()
            tdp_watts = prof.docked_tdp_watts if docked_now else prof.handheld_tdp_watts

            self._record_transition_if_needed(
                prev_docked=prev_docked,
                prev_edid=prev_edid,
                docked_now=docked_now,
                edid_id=edid_id,
                display_name=display_name,
                best_mode=best_mode,
                scaling_decision=scaling_decision,
                builtin_bound=builtin_bound,
                active_ctrls=active_ctrls,
                tdp_watts=tdp_watts,
                charge_limit=charge_limit,
                audio_desc=audio_desc,
            )

            return DaemonStatus(
                deck_model=deck_model,
                is_docked=docked_now,
                ac_online=ac_online,
                active_connector=primary_conn.name if primary_conn else None,
                active_edid_id=self.active_edid_id,
                selected_output_mode=best_mode,
                builtin_controller_bound=builtin_bound,
                active_controllers=active_ctrls,
                sleeping_controllers=sleeping_ctrls,
                unhandled_dongles=self.backend.get_unhandled_dongles(),
                lcd_bluetooth_wakeup_enabled=self.backend.get_lcd_bluetooth_wakeup(),
                charge_limit=charge_limit,
                tdp_watts=tdp_watts,
                last_scaling=scaling_decision,
                audio_sink=audio_desc,
                manual_keep_builtin=self.manual_keep_builtin,
                travel_charge_override=self.travel_charge_override,
                transition_seq=self._transition_seq,
                last_transition=(
                    dict(self._last_transition) if self._last_transition is not None else None
                ),
                last_error=self._last_error,
            )

    def resume_paused_game(self) -> bool:
        """Resume any process held paused during interactive undock modal."""
        with self._lock:
            if self.paused_pid is None:
                return False
            pid = self.paused_pid
            self.paused_pid = None
            self._paused_at = None
            return self.backend.resume_game_process(pid)

    def set_travel_charge_100(self) -> DaemonStatus:
        """Temporarily allow 100% charging while docked before travel."""
        return self.set_travel_charge_override(True)

    def set_travel_charge_override(self, enabled: bool) -> DaemonStatus:
        """Enable or disable the temporary 100% travel charge override."""
        with self._lock:
            self.travel_charge_override = bool(enabled)
            if self.travel_charge_override:
                self.backend.set_charge_limit(-1)
            elif self.is_docked:
                prof = self.store.get_profile(self.active_edid_id)
                self.backend.set_charge_limit(prof.docked_charge_limit)
            else:
                self.backend.set_charge_limit(-1)
            return self.reconcile()

    def set_keep_builtin(self, enabled: bool) -> DaemonStatus:
        """Toggle keeping Steam Deck built-in controls bound while docked."""
        with self._lock:
            self.manual_keep_builtin = bool(enabled)
            if self.manual_keep_builtin:
                self.backend.set_builtin_controller_bound(True)
            return self.reconcile()

    def force_rebind_builtin(self) -> DaemonStatus:
        """Emergency failsafe to restore built-in Deck controls immediately."""
        with self._lock:
            self.manual_keep_builtin = True
            self.backend.set_builtin_controller_bound(True)
            return self.reconcile()

    def get_active_profile(self) -> DockProfile:
        """Return the currently active EDID dock profile or handheld default profile."""
        with self._lock:
            if self.is_docked and self.active_edid_id:
                return self.store.get_profile(self.active_edid_id)
            if self.is_docked:
                return self.store.get_profile("default")
            return self.store.get_handheld_profile()

    def update_active_profile(self, patch: dict[str, Any]) -> DockProfile:
        """Patch and clamp the active profile, invalidate scaling cache, and reapply."""
        with self._lock:
            current = self.get_active_profile()
            merged = current.to_dict()
            if isinstance(patch, dict):
                tv_patch = patch.get("tv")
                if isinstance(tv_patch, dict):
                    merged_tv = dict(merged.get("tv") or {})
                    merged_tv.update(tv_patch)
                    merged["tv"] = merged_tv
                for key, val in patch.items():
                    if key not in ("tv", "profile_id"):
                        merged[key] = val
            updated = DockProfile.from_dict(merged)
            self.store.put_profile(updated)
            self._last_scaling_key = None
            if self.is_docked is True:
                if self.backend.is_ac_online():
                    self.backend.set_tdp_limit(updated.docked_tdp_watts)
                target_cap = -1 if self.travel_charge_override else updated.docked_charge_limit
                self.backend.set_charge_limit(target_cap)
            elif self.is_docked is False:
                self.backend.set_tdp_limit(updated.handheld_tdp_watts)
            if self.is_docked is not None:
                self.reconcile()
            return updated

    def test_active_tv_wake(self) -> bool:
        """Synchronously test waking/switching the active profile's TV."""
        with self._lock:
            prof = self.get_active_profile()
            tv_cfg = replace(prof.tv)
            driver = create_tv_driver(
                tv_cfg.driver,
                cec_trigger=self.backend.trigger_hdmi_cec_wake,
                get_token=self.store.get_token,
                set_token=self.store.set_token,
                get_cert_fingerprint=self.store.get_cert_fingerprint,
                set_cert_fingerprint=self.store.set_cert_fingerprint,
            )
            if driver is None:
                return False
            try:
                ok = driver.wake_and_switch(tv_cfg)
                if ok:
                    self._last_error = None
                return ok
            except Exception as exc:
                self._last_error = str(exc)
                LOG.warning("Active TV wake test failed: %s", exc)
                return False

    def close(self) -> None:
        """Guaranteed crash/shutdown failsafe: never leave Deck buttons unbound."""
        with self._lock:
            LOG.info("Running SwitchDeck shutdown failsafe: rebinding built-in controller.")
            try:
                if self.paused_pid is not None:
                    self.resume_paused_game()
                self.backend.set_builtin_controller_bound(True)
                if self.backend.get_deck_model() == DeckModel.JUPITER_LCD:
                    self.backend.set_lcd_bluetooth_wakeup(False)
            except Exception:
                LOG.exception("Error inside SwitchDeck shutdown failsafe")
            finally:
                try:
                    getattr(self.backend, "close", lambda: None)()
                except Exception:
                    LOG.exception("Error closing SwitchDeck hardware backend")
