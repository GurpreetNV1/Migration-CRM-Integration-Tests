"""Wires app.state for the copied Data Gateway Service integration tests in this folder.

Adapted from server/services/12_data_gateway_service/tests/conftest.py, which always forces an
in-memory backend. This one branches on TEST_GATEWAY_MODE (set by
run_local_integration_tests.py) so the exact same test bodies below can run against either
backend -- the tests themselves only ever call TestClient(app); they have no idea which backend
is behind app.state.gateway.

Unlike every other service here, the Data Gateway Service has no upstream Gateway of its own to
point at -- IT is the thing that talks to Google Sheets/Drive. So "real" mode for this service
means calling its own load_settings() (its normal production config loader), which picks up the
real DATA_BACKEND=google + real credentials from this service's own .env file (see
server/services/12_data_gateway_service/.env.example) -- exactly like a real subprocess of this
service would. No TEST_GATEWAY_URL involved; run_local_integration_tests.py does not need to
start a separate Gateway subprocess for this service's own tests.
"""

import os

from app.main import app, build_app_state
from app.settings import Settings, load_settings

_mode = os.environ.get("TEST_GATEWAY_MODE", "real")

if _mode == "real":
    build_app_state(app, load_settings())
else:
    build_app_state(app, Settings(data_backend="memory"))
