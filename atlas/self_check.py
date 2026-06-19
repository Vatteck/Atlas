"""`atlas --self-check`: print the environment Atlas is running in.

A fast, dependency-light diagnostic for the per-release smoke pass (see
docs/RELEASE_SMOKE.md). It answers "what desktop / display server / tools does this machine
present?" so a manual KDE/GNOME check is deterministic instead of guesswork — the GUI itself
can't be driven headlessly, so this captures the environment-dependent bits that decide which
code paths a given box exercises (tray, terminal launch, mirror regen, no-root update check).

It never constructs the backend managers or creates a window, so it's safe and instant.
"""
import os
import platform
import shutil

# Terminal emulators Atlas knows how to launch pacdiff in (kept loosely in step with
# AtlasApi._find_terminal — this is advisory, exact parity isn't required).
_TERMINALS = ('konsole', 'gnome-terminal', 'alacritty', 'kitty', 'foot',
              'wezterm', 'xfce4-terminal', 'xterm')


def _which_any(*names) -> str:
    """First of `names` found on PATH, as "name (/path)", else ''."""
    for n in names:
        p = shutil.which(n)
        if p:
            return f"{n} ({p})"
    return ""


def gather() -> dict:
    """Environment facts, as an ordered {label: value} dict. Pure/best-effort — never raises."""
    from atlas import __version__

    # Tray + GTK live behind optional system libs (PyGObject / AppIndicator) that aren't in the
    # project venv — import defensively so --self-check works everywhere.
    try:
        from atlas.view.tray import TRAY_AVAILABLE
        tray = bool(TRAY_AVAILABLE)
    except Exception:
        tray = False
    try:
        import gi  # noqa: F401
        gi_ok = True
    except Exception:
        gi_ok = False

    terminal = _which_any(*_TERMINALS) or os.getenv('TERMINAL', '')

    return {
        'Atlas version': __version__,
        'Python': platform.python_version(),
        'Platform': f"{platform.system()} {platform.release()}",
        'Desktop': os.getenv('XDG_CURRENT_DESKTOP') or os.getenv('DESKTOP_SESSION') or '(unset)',
        'Session type': os.getenv('XDG_SESSION_TYPE') or '(unset)',
        'Wayland display': os.getenv('WAYLAND_DISPLAY') or '(none)',
        'X11 display': os.getenv('DISPLAY') or '(none)',
        'PyGObject (gi)': 'yes' if gi_ok else 'NO — GUI/tray need it (it lives in system Python, not the venv)',
        'Tray (AppIndicator/SNI)': 'available' if tray
            else 'unavailable (KDE shows it natively; GNOME needs the AppIndicator extension)',
        'Terminal (pacdiff)': terminal or 'NONE found — set $TERMINAL',
        'pacman': _which_any('pacman') or 'NOT FOUND (not an Arch system?)',
        'AUR helper': _which_any('paru', 'yay', 'pikaur', 'trizen') or 'none',
        'Mirror tool': _which_any('reflector', 'rate-mirrors') or 'none (mirror regeneration disabled)',
        'pacman-contrib': _which_any('checkupdates') or 'none (no-root update check + pacdiff unavailable)',
        'flatpak': _which_any('flatpak') or 'none',
        'git': _which_any('git') or 'none',
        'timeshift': _which_any('timeshift') or 'none',
    }


def run() -> int:
    """Print the diagnostic table. Returns a process exit code (0)."""
    info = gather()
    width = max(len(k) for k in info)
    print("Atlas self-check")
    print("=" * (width + 24))
    for k, v in info.items():
        print(f"  {k.ljust(width)} : {v}")
    return 0
