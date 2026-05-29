"""Gate and instrumentation for the native ``atlas_rs`` (Rust/PyO3) extension.

Every call into the native engine should go through this module so the behaviour is
consistent across call sites and controllable via two environment switches:

* ``ATLAS_DISABLE_RS=1`` — skip the native path entirely and use the pure-Python
  fallback. Useful for A/B comparison and bug triage.
* ``ATLAS_RS_DEBUG=1`` — log (with traceback) when the native module is unavailable,
  raises, or returns a non-success status, instead of silently falling back. Without
  it, failures fall back quietly so the application keeps working.

See ``docs/ROADMAP.md`` (Phase 0) and ``docs/ARCHITECTURE.md`` (§3) for the rationale.
The default behaviour — try native, fall back silently on any problem — is unchanged;
these switches only add visibility and an escape hatch.
"""

import logging
import os
from typing import Optional

_TRUTHY = {'1', 'true', 'yes', 'on'}


def _flag(name: str) -> bool:
    return os.environ.get(name, '').strip().lower() in _TRUTHY


# Read once at import. These are launch-time switches, not per-call toggles.
_RS_DISABLED = _flag('ATLAS_DISABLE_RS')
_RS_DEBUG = _flag('ATLAS_RS_DEBUG')


def native_disabled() -> bool:
    """Whether the native path is force-disabled via ``ATLAS_DISABLE_RS``."""
    return _RS_DISABLED


def debug_enabled() -> bool:
    """Whether native failures should be logged (``ATLAS_RS_DEBUG``)."""
    return _RS_DEBUG


def load(logger: Optional[logging.Logger] = None):
    """Return the ``atlas_rs`` module, or ``None`` to signal "use the Python fallback".

    Returns ``None`` when the native path is disabled or the extension cannot be
    imported (e.g. it was never built). When ``ATLAS_RS_DEBUG`` is set, an import
    failure is logged with a traceback.
    """
    if _RS_DISABLED:
        return None

    try:
        import atlas_rs
        return atlas_rs
    except Exception:
        if _RS_DEBUG and logger is not None:
            logger.warning("atlas_rs native module unavailable; using Python fallback",
                           exc_info=True)
        return None


def report_failure(logger: Optional[logging.Logger], operation: str) -> None:
    """Log a native-path exception when debugging is enabled; otherwise stay silent.

    Call this from the ``except`` block of a native invocation so a broken Rust path
    surfaces as a logged error instead of a silent, slower fallback.
    """
    if _RS_DEBUG and logger is not None:
        logger.warning("atlas_rs.%s raised; using Python fallback", operation,
                       exc_info=True)


def report_non_success(logger: Optional[logging.Logger], operation: str, status) -> None:
    """Log when the native path returned a non-success status and we fall back."""
    if _RS_DEBUG and logger is not None:
        logger.info("atlas_rs.%s returned status=%r; using Python fallback",
                    operation, status)
