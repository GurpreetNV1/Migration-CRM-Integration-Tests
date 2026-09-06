"""Wires app.state for the copied Notes Service integration tests in this folder.

Adapted from server/services/19_notes_service/tests/conftest.py, which always forces an
in-memory Gateway. This one branches on TEST_GATEWAY_MODE (set by
run_local_integration_tests.py) so the exact same test bodies below can run against either
backend -- the tests themselves only ever call TestClient(app); they have no idea which Gateway
implementation is behind app.state.gateway.
"""

import os
import sys
from pathlib import Path

from app.main import app, build_app_state
from app.settings import Settings

# This service's own test_notes_flow.py seeds a prerequisite "note_types" row directly into
# System_Config (admin-module-owned) via app.state.gateway -- fine against the in-memory stand-in,
# rejected by the real Gateway's ownership enforcement. See _foreign_tab_gateway.py, one level up,
# for why and how this is handled in real mode only.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_mode = os.environ.get("TEST_GATEWAY_MODE", "real")

if _mode == "real":
    _gateway_url = os.environ.get("TEST_GATEWAY_URL")
    if not _gateway_url:
        raise RuntimeError(
            "TEST_GATEWAY_MODE=real requires TEST_GATEWAY_URL to be set -- run via "
            "run_local_integration_tests.py, which starts the real Gateway and sets this "
            "automatically."
        )
    # HttpDataGatewayClient's own retry (MAX_ATTEMPTS=3/BACKOFF_BASE_SECONDS=0.5) only rides out
    # ~1.5s -- nowhere near the ~70s a real rolling-quota 503 needs (see
    # integration-tests/gateway_retry.py). Widen it for this subprocess's lifetime only; no
    # production code touched, no revert needed since this subprocess exits once its tests finish.
    from data_gateway_client import http_client as _http_client_module

    _http_client_module.MAX_ATTEMPTS = 3
    _http_client_module.BACKOFF_BASE_SECONDS = 70
    build_app_state(app, Settings(data_gateway_mode="http", data_gateway_url=_gateway_url))
    from _foreign_tab_gateway import ForeignTabAwareGatewayClient

    app.state.gateway = ForeignTabAwareGatewayClient(app.state.gateway, _gateway_url)
else:
    build_app_state(app, Settings(data_gateway_mode="memory"))
