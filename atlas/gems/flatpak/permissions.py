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


# --- editable overrides (Flatseal-style) -----------------------------------------------------
# Generic scheme so one mapping serves both the in-modal quick editor and the full page. A toggle's
# key is "<category>:<value>" (e.g. "socket:x11"). _CATEGORIES maps a category to its [Context] key
# (for reading current state) + the on/off `flatpak override` flag prefixes + the manifest display key.
_CATEGORIES = {
    'share':      ('shared',      '--share=',      '--unshare=',      'share'),
    'socket':     ('sockets',     '--socket=',     '--nosocket=',     'socket'),
    'device':     ('devices',     '--device=',     '--nodevice=',     'device'),
    'feature':    ('features',    '--allow=',      '--disallow=',     'allow'),
    'filesystem': ('filesystems', '--filesystem=', '--nofilesystem=', 'filesystem'),
}

# Full grouped static-toggle spec (Flatseal-style). item = (value, label, detail, risky).
GROUPS = [
    {'category': 'share', 'title': 'Share', 'subtitle': 'Subsystems shared with the host system', 'items': [
        ('network', 'Network', 'Can access the network / internet', True),
        ('ipc', 'Inter-process communication', 'Can share IPC (e.g. X11 SHM) with the host', False),
    ]},
    {'category': 'socket', 'title': 'Socket', 'subtitle': 'Well-known sockets available in the sandbox', 'items': [
        ('x11', 'X11 windowing system', 'Not isolated — other apps can read input or capture its window', True),
        ('wayland', 'Wayland windowing system', 'The sandboxed display server (preferred)', False),
        ('fallback-x11', 'Fallback to X11', 'Uses X11 when Wayland is unavailable', True),
        ('pulseaudio', 'PulseAudio sound server', 'Can play audio and record from the microphone', True),
        ('session-bus', 'D-Bus session bus', 'Full, unfiltered access to the session bus', True),
        ('system-bus', 'D-Bus system bus', 'Full, unfiltered access to the system bus', True),
        ('ssh-auth', 'Secure Shell agent', 'Can use your SSH authentication agent', True),
        ('pcsc', 'Smart cards', 'Can access smart cards', False),
        ('cups', 'Printing system', 'Can talk to the CUPS printing service', False),
        ('gpg-agent', 'GPG agent', 'Can use your GPG agent', True),
        ('inherit-wayland-socket', 'Inherit Wayland socket', 'Inherits the parent process Wayland socket', False),
    ]},
    {'category': 'device', 'title': 'Device', 'subtitle': 'Devices available in the sandbox', 'items': [
        ('dri', 'GPU acceleration', 'Hardware-accelerated graphics', False),
        ('input', 'Input devices', 'Gamepads, joysticks, etc.', True),
        ('usb', 'USB devices', 'Can access USB devices', True),
        ('kvm', 'Virtualization (KVM)', 'Hardware virtualization', True),
        ('shm', 'Shared memory', 'Shared memory with the host', True),
        ('all', 'All devices', 'All devices, including webcams', True),
    ]},
    {'category': 'feature', 'title': 'Features', 'subtitle': 'Extra sandbox features', 'items': [
        ('devel', 'Development syscalls', 'ptrace/perf — used by debuggers', True),
        ('multiarch', 'Multiarch', 'Can run binaries of other architectures', False),
        ('bluetooth', 'Bluetooth', 'Can use Bluetooth', True),
        ('canbus', 'CAN bus', 'Can use the CAN bus', True),
        ('per-app-dev-shm', 'Per-app /dev/shm', 'Uses an isolated /dev/shm', False),
    ]},
]

# The curated subset shown in the in-modal quick editor: (key, label, detail, risky).
_MODAL = [
    ('share:network', 'Network access', 'Can send and receive data over the internet.', True),
    ('socket:x11', 'Legacy windowing (X11)', 'X11 is not isolated — other apps could read its input or capture its window.', True),
    ('socket:wayland', 'Wayland windowing', 'Uses the sandboxed Wayland display server (preferred over X11).', False),
    ('socket:pulseaudio', 'Audio & microphone', 'Can play audio and record from the microphone.', True),
    ('device:all', 'All devices (webcam, etc.)', 'Can access all devices, including webcams and game controllers.', True),
    ('filesystem:home', 'Home folder', 'Can read and write all files in your home folder.', True),
    ('filesystem:host', 'All system files', 'Can read and write all files on the system.', True),
]


def _enabled(key: str, context: Dict[str, set]) -> bool:
    category, _, value = key.partition(':')
    spec = _CATEGORIES.get(category)
    return bool(spec) and value in (context.get(spec[0]) or set())


def parse_context(show_permissions_output: str) -> Dict[str, set]:
    """Parse `flatpak info --show-permissions` [Context] into per-category sets
    (filesystem `:ro`/`:rw` access modes stripped)."""
    cats = {c[0]: set() for c in _CATEGORIES.values()}  # shared/sockets/devices/features/filesystems
    cats['persistent'] = set()
    in_context = False
    for raw in (show_permissions_output or '').splitlines():
        line = raw.strip()
        if line.startswith('['):
            in_context = line == '[Context]'
            continue
        if not in_context or '=' not in line:
            continue
        key, _, val = line.partition('=')
        key = key.strip()
        if key in cats:
            for tok in val.split(';'):
                tok = tok.strip()
                if tok:
                    cats[key].add(tok.split(':', 1)[0] if key == 'filesystems' else tok)
    return cats


def grouped_toggles(context: Dict[str, set]) -> List[Dict]:
    """Full Flatseal-style grouped toggle state for the permissions page."""
    groups = []
    for g in GROUPS:
        display_key = _CATEGORIES[g['category']][3]
        items = [{'key': f"{g['category']}:{value}", 'label': label, 'detail': detail,
                  'flag': f"{display_key}={value}", 'risky': risky,
                  'enabled': _enabled(f"{g['category']}:{value}", context)}
                 for (value, label, detail, risky) in g['items']]
        groups.append({'title': g['title'], 'subtitle': g['subtitle'], 'items': items})
    return groups


def editable_toggles(context: Dict[str, set]) -> List[Dict]:
    """The curated quick-editor toggles (in-modal), with current state."""
    return [{'key': key, 'label': label, 'detail': detail, 'risky': risky, 'enabled': _enabled(key, context)}
            for (key, label, detail, risky) in _MODAL]


def override_flag(key: str, enabled: bool) -> Optional[str]:
    """The `flatpak override --user` flag for a "<category>:<value>" toggle, or None if unknown."""
    category, _, value = key.partition(':')
    spec = _CATEGORIES.get(category)
    if not spec or not value:
        return None
    return (spec[1] if enabled else spec[2]) + value


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
