"""Password derivation rules for PDF T4 pipeline. Uses Box12 first, Box13 fallback."""
import re


def _derive_from_value(value: str, box_label: str) -> tuple[bool, str]:
    """Derive password from a single box value. Rules: all digits OK; contains RT -> digits before RT."""
    trimmed = (value or "").strip()
    if not trimmed:
        return False, f"{box_label} invalid: empty"
    if trimmed.isdigit():
        return True, trimmed
    match = re.search(r"^(\d+)\s*[Rr][Tt]", trimmed)
    if match:
        return True, match.group(1)
    return False, f"{box_label} invalid: must be all digits or digits before RT"


def derive_password(box12_raw: str, box13_raw: str | None = None) -> tuple[bool, str]:
    """
    Derive password from Box12 (primary) or Box13 (fallback).

    Rules:
    1) If Box12 has value -> use it: all digits OK, or digits before RT
    2) Else if Box13 has value -> use it: all digits OK, or digits before RT
    3) Else -> fail

    Returns:
        (ok: bool, password_or_reason: str)
    """
    box12_trimmed = (box12_raw or "").strip()
    if box12_trimmed:
        return _derive_from_value(box12_raw, "Box12")

    box13_trimmed = (box13_raw or "").strip()
    if box13_trimmed:
        return _derive_from_value(box13_raw, "Box13")

    return False, "Box12 and Box13 invalid: both empty; need all digits or digits before RT"


def derive_password_from_box12(box12_raw: str) -> tuple[bool, str]:
    """Legacy: derive from Box12 only. Use derive_password() for Box12+Box13 fallback."""
    return derive_password(box12_raw, None)
