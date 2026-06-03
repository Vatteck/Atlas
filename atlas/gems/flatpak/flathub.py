"""Flathub v2 (AppStream-based) API client + response-shape mapping.

Flathub retired the v1 REST API (`/api/v1/apps/{id}` now returns 404). This module owns the
v2 endpoints and translates their AppStream-shaped JSON into the flat values Atlas consumes,
so the rest of the Flatpak gem never sees raw v2 payloads. See
docs/plans/2026-06-01-flathub-v2-api-migration.md for the field mapping.
"""
from datetime import datetime
from typing import List, Optional

from atlas.commons.html import strip_html
from atlas.gems.flatpak.constants import FLATHUB_API_URL


def get_appstream(http_client, app_id: str, logger=None) -> Optional[dict]:
    """Fetch the v2 AppStream component for an app id, or None if unavailable.

    Uses a single (non-retried) request: a 404 is a definitive "this app isn't on
    Flathub" — common for apps installed from other remotes — so retrying is wasteful and
    a warning is too loud. `single_call=True` also returns before the http client's own
    "Could not retrieve data" WARNING, keeping the missing-app case quiet (DEBUG)."""
    if not app_id:
        return None

    res = http_client.get('{}/appstream/{}'.format(FLATHUB_API_URL, app_id), single_call=True)

    if res is None:  # network error; the http client already logged it
        return None

    if 200 <= res.status_code < 300:
        try:
            return res.json()
        except ValueError:
            return None

    if logger is not None:
        logger.debug("Flathub has no v2 AppStream entry for '%s' (HTTP %s)", app_id, res.status_code)
    return None


def latest_release(data: Optional[dict]) -> dict:
    """The most recent release block (v2 lists releases newest-first), or {}."""
    releases = (data or {}).get('releases') or []
    return releases[0] if releases else {}


def categories(data: Optional[dict]) -> List[str]:
    """v2 categories are a list of plain strings (v1 was a list of {'name': ...})."""
    return [c for c in ((data or {}).get('categories') or []) if isinstance(c, str)]


def screenshot_urls(data: Optional[dict]) -> List[str]:
    """One image URL per screenshot — the largest available source.

    v2 screenshots are `{'caption', 'sizes': [{'width','height','scale','src'}, ...]}`;
    v1 exposed a single `imgDesktopUrl`. We pick the widest `src` so the viewer still gets
    a full-size image.
    """
    urls = []

    for shot in (data or {}).get('screenshots') or []:
        best_src, best_width = None, -1

        for size in shot.get('sizes') or []:
            src = size.get('src')
            if not src:
                continue

            try:
                width = int(size.get('width') or 0)
            except (TypeError, ValueError):
                width = 0

            if width > best_width:
                best_src, best_width = src, width

        if best_src:
            urls.append(best_src)

    return urls


def app_info(data: Optional[dict]) -> dict:
    """A curated, display-ready dict for the info panel of a not-installed app."""
    if not data:
        return {}

    release = latest_release(data)
    info = {
        'name': data.get('name'),
        'summary': data.get('summary'),
        'description': strip_html(data['description']) if data.get('description') else None,
        'version': release.get('version'),
        'developer': data.get('developer_name'),
        'license': data.get('project_license'),
        'homepage': (data.get('urls') or {}).get('homepage'),
        'categories': ', '.join(categories(data)) or None,
        'release_date': _release_date(release),
        'release_notes': strip_html(release['description']) if release.get('description') else None,
    }
    # drop empties so the panel doesn't show blank rows
    return {k: v for k, v in info.items() if v}


def metadata_badges(data: Optional[dict]) -> dict:
    """Display badges from the v2 AppStream payload: license FOSS/proprietary + developer
    verification. (Downloads come separately from the stats endpoint.) Empty dict if no data."""
    if not data:
        return {}
    meta = data.get('metadata') or {}
    return {
        'license': data.get('project_license'),
        'is_free': bool(data.get('is_free_license')),
        'verified': bool(meta.get('flathub::verification::verified')),
        'verified_via': meta.get('flathub::verification::website')
                        or meta.get('flathub::verification::login_provider') or None,
    }


def installs_last_month(http_client, app_id: str, logger=None) -> Optional[int]:
    """Monthly install count from the Flathub stats endpoint, or None. Best-effort."""
    if not app_id:
        return None
    try:
        res = http_client.get('{}/stats/{}'.format(FLATHUB_API_URL, app_id), single_call=True)
        if res is not None and 200 <= res.status_code < 300:
            return res.json().get('installs_last_month')
    except Exception as e:
        if logger is not None:
            logger.debug("flathub stats fetch failed for '%s': %s", app_id, e)
    return None


def permissions(http_client, app_id: str, logger=None) -> Optional[dict]:
    """The structured Flatpak permission set (sockets/filesystems/devices/shared/session-bus/…)
    from the Flathub `summary` endpoint — available for any app, installed or not. None on miss."""
    if not app_id:
        return None
    try:
        res = http_client.get('{}/summary/{}'.format(FLATHUB_API_URL, app_id), single_call=True)
        if res is not None and 200 <= res.status_code < 300:
            return (res.json().get('metadata') or {}).get('permissions') or {}
    except Exception as e:
        if logger is not None:
            logger.debug("flathub summary/permissions fetch failed for '%s': %s", app_id, e)
    return None


def _release_date(release: dict) -> Optional[datetime]:
    """v2 releases carry a unix `timestamp` (string) and sometimes an ISO `date`."""
    ts = release.get('timestamp')
    if ts is not None:
        try:
            return datetime.fromtimestamp(int(ts))
        except (TypeError, ValueError, OSError):
            pass

    date = release.get('date')
    if date:
        try:
            return datetime.strptime(date, '%Y-%m-%d')
        except (TypeError, ValueError):
            pass

    return None
