import subprocess
from pathlib import Path


def test_main_js_frontend_state_contracts():
    repo = Path(__file__).resolve().parents[3]
    subprocess.run(
        ["node", "tests/view/webview/main_js_contracts.test.js"],
        cwd=repo,
        check=True,
    )
