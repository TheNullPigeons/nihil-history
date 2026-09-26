from nihil_history.services import _normalize_pasted_utf16le_secret


def test_normalizes_utf16le_paste_with_terminal_backspaces():
    secret = "correct-secret"
    malformed = secret.encode("utf-16le").decode("latin-1") + "\x08" * 8

    assert _normalize_pasted_utf16le_secret(malformed) == secret


def test_preserves_normal_secret():
    assert _normalize_pasted_utf16le_secret("+O6+BKwJ0E5e") == "+O6+BKwJ0E5e"


def test_preserves_non_utf16_nul_secret():
    value = "abc\x00def"
    assert _normalize_pasted_utf16le_secret(value) == value
