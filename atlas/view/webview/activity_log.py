import os
import json
import datetime
import threading
from typing import List

LOG_FILE = os.path.expanduser('~/.cache/atlaspm/activity.jsonl')
_log_lock = threading.Lock()

def record_activity(action: str, pkg_name: str, pkg_type: str, success: bool, error: str = None):
    """
    Appends an activity log entry to ~/.cache/bauh/activity.jsonl
    """
    entry = {
        'timestamp': datetime.datetime.now().isoformat(),
        'action': action,
        'pkg_name': pkg_name,
        'pkg_type': pkg_type,
        'success': success,
        'error': error
    }
    
    with _log_lock:
        try:
            os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
            with open(LOG_FILE, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry) + '\n')
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
