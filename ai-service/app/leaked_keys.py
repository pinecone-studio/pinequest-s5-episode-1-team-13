"""Keys that leaked into the public git history (commits 6edc58d, d88caf6, ac55346 — see SECURITY.md).

Only SHA-256 hashes are kept here (the values cannot be recovered from them). On start-up the service compares its
own keys with these and logs a SECURITY error while an old key is still in use. It does not refuse to start.
"""

from __future__ import annotations

import hashlib
from urllib.parse import urlsplit

LEAKED_SHA256 = {
    "INTERNAL_API_KEY": {"be4e54f59bf8f852543ed6e7fda3d09a1d9e3231e7dc8838940289516ae609a1"},
    "CAMERA_SECRET_KEY": {"9c6860a2195991cb09e5bb507d066ae3dbf48bbb94415bb3ac4ab3155f398e11"},
    "JWT_SECRET": {"2704dbd8b830dff96c1cdc563fec7a0d850f9736fec71d33621157b84d68bce5"},
    "SUPABASE_SERVICE_ROLE_KEY": {"fe9d3b1d55a56c5c9aeac9c76024541352a182fdf45631358d04eee1bb0d298a"},
    "DATABASE_URL": {"2de34fc72e6dee46f065d3a7ce9cfa93105d8f3875794b94bd4af4f1e7ec145d"},  # нууц үгийн hash
}


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def leaked_names(values: dict[str, str]) -> list[str]:
    """{"INTERNAL_API_KEY": "...", "DATABASE_URL": "postgresql://..."} -> задарсан хэвээр байгаа нэрс."""
    found = []
    for name, value in values.items():
        if not value or name not in LEAKED_SHA256:
            continue
        if name == "DATABASE_URL":
            try:
                value = urlsplit(value).password or ""
            except ValueError:
                continue
        if value and _digest(value) in LEAKED_SHA256[name]:
            found.append(name)
    return found
