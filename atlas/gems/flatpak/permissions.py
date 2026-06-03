"""Map a Flatpak permission set (from Flathub's `summary` endpoint: metadata.permissions) to
human-readable, risk-rated items plus an overall *advisory* safety tier — mirroring how GNOME
Software / Flathub present an app's sandbox.

ADVISORY ONLY. This describes the permissions an app *declares*, not what it actually does.
"Potentially unsafe" means "has broad access worth understanding before installing", NOT "is
malware". A clean result does not mean an app is trustworthy. Never present it as a safety verdict.
"""
from typing import Dict, List, Optional

SAFE, WARN, DANGER = 'safe', 'warn', 'danger'


def _filesystem_item(fs: str):
    f = (fs or '').strip()
    low = f.lower()
    # Strip an explicit access mode suffix (":ro"/":rw"/":create") for matching.
    base = low.split(':', 1)[0]
    if base in ('host', 'host-os', 'host-etc'):
        return ('All system files', 'Can read and write files across the whole system', DANGER)
    if base == 'home':
        return ('Home folder access', 'Can read and write all data in your home folder', DANGER)
    if base.startswith('xdg-'):
        return (f'{f} folder', 'Can read and write this user folder', WARN)
    if base.startswith('/') or base.startswith('~'):
        return (f'Filesystem path {f}', 'Can read and write all data in this path', DANGER)
    return (f'Filesystem: {f}', 'Filesystem access outside the sandbox', WARN)


# socket token -> (title, detail, level). Unlisted sockets fall through to a generic WARN.
_SOCKETS = {
    'x11': ('Legacy windowing (X11)', 'Uses X11, which is not isolated from other windows', DANGER),
    'fallback-x11': ('Legacy windowing (X11 fallback)', 'Falls back to X11, which is not isolated', WARN),
    'wayland': ('Wayland windowing', 'Uses the sandboxed Wayland display server', SAFE),
    'pulseaudio': ('Audio & microphone', 'Can play audio and listen via the microphone', WARN),
    'session-bus': ('Full session bus access', 'Unrestricted access to the session D-Bus', DANGER),
    'system-bus': ('Full system bus access', 'Unrestricted access to the system D-Bus', DANGER),
    'ssh-auth': ('SSH agent', 'Can use your SSH authentication agent', WARN),
    'cups': ('Printing', 'Can talk to the printing system', SAFE),
    'gpg-agent': ('GPG agent', 'Can use your GPG agent', WARN),
}

_DEVICES = {
    'all': ('All devices', 'Can access all devices, including webcams and controllers', DANGER),
    'dri': ('GPU acceleration', 'Can use hardware GPU acceleration', SAFE),
    'input': ('Input devices', 'Can access input devices (gamepads, etc.)', WARN),
    'kvm': ('Virtualization (KVM)', 'Can use hardware virtualization', WARN),
    'shm': ('Shared memory', 'Can use shared memory with the host', WARN),
}

_SHARED = {
    'network': ('Network access', 'Has full network access', WARN),
    # 'ipc' is low-risk plumbing (shared X11 SHM, etc.) — not surfaced.
}


def describe(perms: Optional[Dict], is_free: bool = True) -> List[Dict]:
    """Human-readable, risk-rated permission items. Ordered danger-ish first by category."""
    perms = perms or {}
    items: List[Dict] = []

    for fs in perms.get('filesystems') or []:
        title, detail, level = _filesystem_item(fs)
        items.append({'title': title, 'detail': detail, 'level': level})

    for sock in perms.get('sockets') or []:
        s = (sock or '').strip().lower()
        title, detail, level = _SOCKETS.get(s, (f'Socket: {sock}', 'Access to a host socket', WARN))
        items.append({'title': title, 'detail': detail, 'level': level})

    for dev in perms.get('devices') or []:
        d = (dev or '').strip().lower()
        title, detail, level = _DEVICES.get(d, (f'Device: {dev}', 'Access to a host device', WARN))
        items.append({'title': title, 'detail': detail, 'level': level})

    for sh in perms.get('shared') or []:
        s = (sh or '').strip().lower()
        if s in _SHARED:
            title, detail, level = _SHARED[s]
            items.append({'title': title, 'detail': detail, 'level': level})

    # Talking to / owning D-Bus names outside the portal sandbox.
    for bus in ('session-bus', 'system-bus'):
        policy = perms.get(bus)
        if isinstance(policy, dict) and (policy.get('own') or policy.get('talk')):
            items.append({'title': 'Uses non-portal services',
                          'detail': 'Can talk to D-Bus services outside the sandbox',
                          'level': WARN})

    if not is_free:
        items.append({'title': 'Proprietary code',
                      'detail': "Source isn't public, so it can't be independently audited",
                      'level': WARN})

    # danger first, then warn, then safe — stable within a level
    order = {DANGER: 0, WARN: 1, SAFE: 2}
    items.sort(key=lambda i: order.get(i['level'], 1))
    return items


_LABELS = {'unsafe': 'Potentially unsafe', 'moderate': 'Limited sandbox', 'safe': 'Sandboxed'}


def safety(perms: Optional[Dict], is_free: bool = True) -> Dict:
    """Advisory overall tier from the permission set + license. unsafe > moderate > safe."""
    items = describe(perms, is_free)
    if any(i['level'] == DANGER for i in items):
        level = 'unsafe'
    elif any(i['level'] == WARN for i in items):
        level = 'moderate'
    else:
        level = 'safe'
    return {'level': level, 'label': _LABELS[level]}
