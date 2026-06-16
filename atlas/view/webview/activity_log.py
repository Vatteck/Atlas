import os
import json
import datetime
import threading
from typing import List

LOG_FILE = os.path.expanduser('~/.cache/atlaspm/activity.jsonl')
MAX_ACTIVITY_ENTRIES = 1000
COMPACT_EVERY_WRITES = 25
_write_count = 0
_log_lock = threading.Lock()

def _compact_activity_log(max_entries: int = MAX_ACTIVITY_ENTRIES):
    """Keep only the newest valid JSONL entries. Caller must hold ``_log_lock``."""
    if max_entries <= 0 or not os.path.exists(LOG_FILE):
        return
    entries = []
    with open(LOG_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                json.loads(line)
                entries.append(line)
            except Exception:
                pass
    if len(entries) <= max_entries:
        return
    with open(LOG_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(entries[-max_entries:]) + '\n')


def record_activity(action: str, pkg_name: str, pkg_type: str, success: bool, error: str = None):
    """
    Appends an activity log entry to ~/.cache/atlaspm/activity.jsonl
    """
    entry = {
        'timestamp': datetime.datetime.now().isoformat(),
        'action': action,
        'pkg_name': pkg_name,
        'pkg_type': pkg_type,
        'success': success,
        'error': error
    }
    
    global _write_count
    with _log_lock:
        try:
            os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
            with open(LOG_FILE, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry) + '\n')
            _write_count += 1
            if _write_count >= COMPACT_EVERY_WRITES:
                _compact_activity_log(MAX_ACTIVITY_ENTRIES)
                _write_count = 0
        except Exception as e:
            # We don't want activity logging to crash the app, but log it to stdout/stderr
            print(f"[activity_log] Error recording activity: {e}")

def get_activity_log(limit: int = 50) -> List[dict]:
    """
    Reads the chronological activity log, returning a list of entries, latest first.
    """
    entries = []
    if not os.path.exists(LOG_FILE):
        return entries
        
    with _log_lock:
        try:
            with open(LOG_FILE, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except Exception:
                            pass
        except Exception as e:
            print(f"[activity_log] Error reading activity log: {e}")
            
    # Return reversed to have newest first, limited
    return entries[::-1][:limit]


def clear_activity_log() -> bool:
    """Delete the activity log file (the History page's "Clear" action). Thread-safe; a missing file
    is already-cleared (returns True). Returns False only on an actual removal error."""
    with _log_lock:
        try:
            if os.path.exists(LOG_FILE):
                os.remove(LOG_FILE)
            return True
        except Exception as e:
            print(f"[activity_log] Error clearing activity log: {e}")
            return False


EXPORT_PATH = os.path.expanduser('~/atlas-activity.json')


def export_activity_log(path: str = EXPORT_PATH) -> str:
    """Write the full activity log (newest first) to a JSON file the user can keep/script against.
    Returns the path written. Raises on a write failure (the caller reports it)."""
    entries = get_activity_log(limit=10000)
    payload = {
        'exported': datetime.datetime.now().isoformat(),
        'version': 1,
        'count': len(entries),
        'activity': entries,
    }
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return path
