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


def get_appstream(http_client, app_id: str) -> Optional[dict]:
    """Fetch the v2 AppStream component for an app id, or None if unavailable."""
    if not app_id:
        return None
    return http_client.get_json('{}/appstream/{}'.format(FLATHUB_API_URL, app_id))


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
