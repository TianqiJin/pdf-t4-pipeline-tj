"""Tests for password_rules module."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lambdas"))

from shared.password_rules import derive_password, derive_password_from_box12


def test_all_digits_returns_trimmed():
    """Trimmed all digits -> password = trimmed."""
    ok, pwd = derive_password_from_box12("  12345  ")
    assert ok is True
    assert pwd == "12345"


def test_digits_before_rt():
    """Contains RT and digits before -> password = digits before RT."""
    ok, pwd = derive_password_from_box12("12345RT")
    assert ok is True
    assert pwd == "12345"

    ok, pwd = derive_password_from_box12("99 rt")
    assert ok is True
    assert pwd == "99"


def test_invalid_fails():
    """Invalid Box12 fails with reason."""
    ok, reason = derive_password_from_box12("abc")
    assert ok is False
    assert "Box12 invalid" in reason


def test_derive_password_box12_primary():
    """Box12 used when present. Box13 ignored."""
    ok, pwd = derive_password("111222333", "444555666")
    assert ok is True
    assert pwd == "111222333"


def test_derive_password_box13_fallback():
    """Box13 used when Box12 empty."""
    ok, pwd = derive_password("", "123456789")
    assert ok is True
    assert pwd == "123456789"

    ok, pwd = derive_password("", "999888777RT")
    assert ok is True
    assert pwd == "999888777"


def test_derive_password_both_empty_fails():
    """Both empty -> fail."""
    ok, reason = derive_password("", "")
    assert ok is False
    assert "both empty" in reason


def test_derive_password_box13_invalid_fails():
    """Box13 fallback with invalid value fails."""
    ok, reason = derive_password("", "invalid")
    assert ok is False
    assert "Box13 invalid" in reason
