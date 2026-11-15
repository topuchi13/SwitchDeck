"""Universal 'Whatever Config They Have' scaling engine for Gamescope."""

from __future__ import annotations

from .domain import (
    DisplayMode,
    DockProfile,
    GameWindowState,
    GamescopeFilter,
    GamescopeScaler,
    ScalingDecision,
)

HANDHELD_WIDTH = 1280
HANDHELD_HEIGHT = 800

# Step-down ladder if a resizable game maxes out the Deck APU at 1080p+
STEP_DOWN_LADDER: tuple[tuple[int, int], ...] = (
    (1920, 1080),
    (1600, 900),
    (1280, 720),
)


def _step_down_resolution(current_width: int, current_height: int) -> tuple[int, int]:
    for w, h in STEP_DOWN_LADDER:
        if h < current_height:
            return (w, h)
    return (1280, 720)


def compute_universal_scaling(
    is_docked: bool,
    output_mode: DisplayMode | None,
    game: GameWindowState | None,
    profile: DockProfile,
    consecutive_gpu_overload: int = 0,
    vrr_capable: bool = False,
) -> ScalingDecision:
    """Choose live Gamescope XWayland size and scaling filter for ANY game.

    Works zero-config across:
    - Resizable SDL2/RT64 ports (Zelda64Recomp, Ship of Harkinian) that jump
      from 1280x800 -> 1920x1080 live via GAMESCOPE_XWAYLAND_MODE_CONTROL.
    - Fixed-config Proton/AAA games locked at 720p/800p -> auto FSR + FIT.
    - Retro low-res games (<= 540p) -> PIXEL + INTEGER scaling.
    - GPU-bound 1080p titles (>= 97% GPU busy across samples) -> adaptive step-down
      with FSR enabled.
    """
    if not is_docked or output_mode is None:
        return ScalingDecision(
            target_width=HANDHELD_WIDTH,
            target_height=HANDHELD_HEIGHT,
            scaling_filter=GamescopeFilter.LINEAR,
            scaling_scaler=GamescopeScaler.FIT,
            fsr_sharpness=profile.fsr_sharpness,
            allow_super_res=False,
            enable_vrr=False,
            reason="handheld native 1280x800",
        )

    # Offer 16:9 docked container capped by the physical output resolution
    offer_w = min(profile.preferred_container_width, output_mode.width)
    offer_h = min(profile.preferred_container_height, output_mode.height)
    if offer_w <= 0 or offer_h <= 0:
        offer_w, offer_h = 1920, 1080

    # No active game window yet (Steam UI or loading): prepare 1080p container + FSR fallback
    if game is None or game.width <= 0 or game.height <= 0:
        needs_upscale = offer_h < output_mode.height
        return ScalingDecision(
            target_width=offer_w,
            target_height=offer_h,
            scaling_filter=GamescopeFilter.FSR if needs_upscale else GamescopeFilter.LINEAR,
            scaling_scaler=GamescopeScaler.FIT,
            fsr_sharpness=profile.fsr_sharpness,
            allow_super_res=False,
            enable_vrr=vrr_capable,
            reason="docked menu/idle container ready",
        )

    # Adaptive GPU overload step-down (only if enabled and sustained >= 2 ticks)
    if (
        profile.adaptive_gpu_downscale
        and consecutive_gpu_overload >= 2
        and game.height >= 900
        and (game.gpu_busy_percent or 0) >= 97
    ):
        down_w, down_h = _step_down_resolution(game.width, game.height)
        return ScalingDecision(
            target_width=down_w,
            target_height=down_h,
            scaling_filter=GamescopeFilter.FSR,
            scaling_scaler=GamescopeScaler.FIT,
            fsr_sharpness=profile.fsr_sharpness,
            allow_super_res=False,
            enable_vrr=vrr_capable,
            reason=f"gpu busy {game.gpu_busy_percent}% -> step down to {down_w}x{down_h} + FSR",
        )

    # Retro / pixel-art low-resolution detection (<= 540p)
    if game.height <= 540:
        return ScalingDecision(
            target_width=offer_w,
            target_height=offer_h,
            scaling_filter=GamescopeFilter.PIXEL,
            scaling_scaler=GamescopeScaler.INTEGER,
            fsr_sharpness=profile.fsr_sharpness,
            allow_super_res=False,
            enable_vrr=vrr_capable,
            reason=f"retro {game.width}x{game.height} -> PIXEL + INTEGER",
        )

    # Sub-native game window (e.g., locked 720p/800p on 1080p/4K TV, or 1080p on 4K TV)
    if game.height < output_mode.height or game.width < output_mode.width:
        return ScalingDecision(
            target_width=offer_w,
            target_height=offer_h,
            scaling_filter=GamescopeFilter.FSR,
            scaling_scaler=GamescopeScaler.FIT,
            fsr_sharpness=profile.fsr_sharpness,
            allow_super_res=False,
            enable_vrr=vrr_capable,
            reason=f"upscale {game.width}x{game.height} -> {output_mode.width}x{output_mode.height} via FSR",
        )

    # Exact 1:1 native match
    return ScalingDecision(
        target_width=offer_w,
        target_height=offer_h,
        scaling_filter=GamescopeFilter.LINEAR,
        scaling_scaler=GamescopeScaler.FIT,
        fsr_sharpness=profile.fsr_sharpness,
        allow_super_res=False,
        enable_vrr=vrr_capable,
        reason=f"native 1:1 match at {game.width}x{game.height}",
    )
