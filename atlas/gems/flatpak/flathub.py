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
    
    # Parse age rating from AppStream v2 content_rating_details
    age_rating = None
    crd = data.get('content_rating_details')
    if crd and isinstance(crd, dict):
        en_us = crd.get('en_US', {})
        if 'minimumAge' in en_us:
            age = en_us['minimumAge']
            age_rating = f"{age}+" if age > 0 else "All Ages"

    return {
        'license': data.get('project_license'),
        'is_free': bool(data.get('is_free_license')),
        'verified': bool(meta.get('flathub::verification::verified')),
        'verified_via': meta.get('flathub::verification::website')
                        or meta.get('flathub::verification::login_provider') or None,
        'content_rating': age_rating,
        'desktop_only': data.get('type') == 'desktop-application',
        'developer_name': data.get('developer_name')
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


def map_collection_hit(hit: Optional[dict]) -> Optional[dict]:
    """Flatten one hit from the `/collection/category/<cat>` payload into the fields the
    Browse view needs, or None if it has no usable app id. The collection hit carries a
    dotted `app_id` (the `id` field is the underscore-joined search doc id — don't use it)."""
    if not hit:
        return None
    app_id = hit.get('app_id')
    if not app_id:
        return None
    return {
        'id': app_id,
        'name': hit.get('name') or app_id,
        'description': strip_html(hit.get('summary') or '') or None,
        'icon_url': hit.get('icon') or None,
        'developer_name': hit.get('developer_name') or None,
        'is_free': bool(hit.get('is_free_license')),
        'verified': bool(hit.get('verification_verified')),
    }


def collection_apps(http_client, category: str, limit: int = 60, logger=None) -> List[dict]:
    """Apps in a Flathub top-level category, newest-list order, as flat dicts (see
    `map_collection_hit`). One best-effort request; returns [] on any miss/error so the
    Browse view is never blocked by Flathub being slow or down."""
    if not category:
        return []
    try:
        per_page = limit if limit and limit > 0 else 60
        res = http_client.get('{}/collection/category/{}?page=1&per_page={}'.format(
            FLATHUB_API_URL, category, per_page), single_call=True)
        if res is None or not (200 <= res.status_code < 300):
            return []
        hits = (res.json() or {}).get('hits') or []
    except Exception as e:
        if logger is not None:
            logger.debug("flathub collection fetch failed for '%s': %s", category, e)
        return []

    apps = [m for m in (map_collection_hit(h) for h in hits) if m]
    return apps[:limit] if limit and limit > 0 else apps


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
