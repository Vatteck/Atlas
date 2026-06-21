import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which('node') is None,
                    reason="node not installed; the dedicated CI 'js' job runs these contracts")
def test_main_js_frontend_state_contracts():
    repo = Path(__file__).resolve().parents[3]
    subprocess.run(
        ["node", "tests/view/webview/main_js_contracts.test.js"],
        cwd=repo,
        check=True,
    )
