"""Bridge the mentoring reference port to the NCS lookup API."""
from typing import Any


class ReferenceUnitAdapter:
    def __init__(self, lookup: Any) -> None:
        self._lookup = lookup

    def get_competency_unit(self, unit_code: str):
        ncs_code = unit_code[:8]
        if len(ncs_code) != 8 or not ncs_code.isdigit():
            return None
        return self._lookup.get_unit(ncs_code, unit_code)
