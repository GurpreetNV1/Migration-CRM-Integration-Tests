"""Real-mode-only helper: lets a service's own copied test-seed helpers write prerequisite rows
into tabs owned by ANOTHER service (e.g. Admin Module's System_Config/RFI_Type_Config/
Application_Type_Field_Schemas, or User Service's Contact) exactly like production requires.

Why this exists: several copied test files' own module-level seed helpers (e.g.
application/test_application_flow.py's _seed_schema) call app.state.gateway.create(...) directly
to set up a prerequisite row owned by a different service -- a shortcut that only worked against
the in-memory Gateway stand-in, which never checks caller identity. The real Data Gateway Service
enforces per-tab ownership (see server/services/12_data_gateway_service/app/config.py's
TAB_OWNERSHIP) and correctly rejects a create() for a tab this service doesn't own with a 403,
exactly as it would for a real rogue write in production. This wrapper transparently routes just
those known cross-service creates through a second HttpDataGatewayClient instantiated with the
correct owning service's identity -- same pattern the top-level integration-tests/conftest.py's
own seed_gateway_record(..., caller=...) already uses for the 11 cross-service tests. Every other
call (get/update/delete/query, and any tab this service does own) goes through the original real
client unchanged.

Used only by copied conftest.py files' real-mode branch -- memory mode never needed ownership
enforcement in the first place, so it never needs this wrapper either.
"""

from __future__ import annotations

from typing import Any

from data_gateway_client import HttpDataGatewayClient

# Only the tabs actually seeded cross-service by a copied test file's own setup helpers today --
# see server/services/12_data_gateway_service/app/config.py's TAB_OWNERSHIP for the full map.
FOREIGN_TAB_OWNERS: dict[str, str] = {
    "Application_Type_Field_Schemas": "admin-module",
    "Compliance_Checklist_Item": "admin-module",
    "RFI_Type_Config": "admin-module",
    "Notification_Type_Config": "admin-module",
    "System_Config": "admin-module",
    "Discount_Coupon": "admin-module",
    "Role_Hierarchy": "admin-module",
    "Audit_Log": "audit-service",
    "Reminders_History": "reminder-service",
    "Contact": "user-service",
    "Application": "application-service",
}


class ForeignTabAwareGatewayClient:
    def __init__(self, own_client: Any, gateway_url: str) -> None:
        self._own = own_client
        self._gateway_url = gateway_url
        self._foreign_clients: dict[str, Any] = {}

    def _foreign_client_for(self, owner: str) -> Any:
        if owner not in self._foreign_clients:
            self._foreign_clients[owner] = HttpDataGatewayClient(self._gateway_url, owner)
        return self._foreign_clients[owner]

    def create(self, tab: str, fields: dict[str, Any]) -> Any:
        owner = FOREIGN_TAB_OWNERS.get(tab)
        if owner is not None:
            return self._foreign_client_for(owner).create(tab, fields)
        return self._own.create(tab, fields)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._own, name)
