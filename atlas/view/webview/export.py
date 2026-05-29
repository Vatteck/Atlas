import os
import json
import datetime

MANIFEST_PATH = os.path.expanduser('~/atlas-manifest.json')

def write_manifest(packages: list) -> str:
    manifest = {
        'created': datetime.datetime.now().isoformat(),
        'version': 1,
        'packages': packages
    }
    with open(MANIFEST_PATH, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    return MANIFEST_PATH

def read_manifest() -> list:
    if not os.path.exists(MANIFEST_PATH):
        raise FileNotFoundError(f"Manifest not found at {MANIFEST_PATH}")
    with open(MANIFEST_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data.get('packages', [])
