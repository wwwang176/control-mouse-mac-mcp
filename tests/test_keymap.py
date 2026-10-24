import pytest

from control_mouse_mac_mcp.keymap import (
    FLAG_ALT,
    FLAG_CMD,
    FLAG_CTRL,
    FLAG_SHIFT,
    KeyNameError,
    parse_combo,
    parse_modifiers,
)


def test_single_key():
    combo = parse_combo("enter")
    assert [k.code for k in combo] == [36]
    assert combo[0].flag == 0


def test_aliases_map_to_same_code():
    assert parse_combo("return")[0].code == parse_combo("enter")[0].code
    assert parse_combo("esc")[0].code == parse_combo("escape")[0].code


def test_combo_keeps_order_and_flags():
    combo = parse_combo("cmd+shift+s")
    assert [k.code for k in combo] == [55, 56, 1]
    assert combo[0].flag == FLAG_CMD
    assert combo[1].flag == FLAG_SHIFT
    assert combo[2].flag == 0


def test_case_and_whitespace_insensitive():
    assert parse_combo(" Ctrl + C ") == parse_combo("ctrl+c")


def test_win_is_cmd_alias():
    assert parse_combo("win+c") == parse_combo("cmd+c")
    assert parse_combo("windows")[0].flag == FLAG_CMD


def test_ctrl_is_real_control_not_cmd():
    ctrl = parse_combo("ctrl")[0]
    assert ctrl.code == 59
    assert ctrl.flag == FLAG_CTRL


def test_alt_and_option_are_same():
    assert parse_combo("alt") == parse_combo("option") == parse_combo("opt")
    assert parse_combo("alt")[0].flag == FLAG_ALT


def test_delete_is_forward_delete_and_backspace_is_delete_key():
    assert parse_combo("delete")[0].code == 117
    assert parse_combo("backspace")[0].code == 51


def test_letters_digits_function_keys():
    assert parse_combo("a")[0].code == 0
    assert parse_combo("z")[0].code == 6
    assert parse_combo("0")[0].code == 29
    assert parse_combo("f1")[0].code == 122
    assert parse_combo("f12")[0].code == 111


def test_punctuation():
    assert parse_combo("cmd+,")[1].code == 43
    assert parse_combo("cmd+=")[1].code == 24
    assert parse_combo("cmd+-")[1].code == 27


@pytest.mark.parametrize("key", ["insert", "printscreen", "numlock"])
def test_windows_only_keys_are_rejected_with_hint(key):
    with pytest.raises(KeyNameError, match="not available on macOS"):
        parse_combo(key)


def test_unknown_key_lists_available():
    with pytest.raises(KeyNameError, match="Unknown key: foo.*Available:.*enter"):
        parse_combo("ctrl+foo")


def test_empty_part_rejected():
    with pytest.raises(KeyNameError):
        parse_combo("ctrl+")


def test_parse_modifiers():
    assert parse_modifiers(None) == []
    assert parse_modifiers("") == []
    mods = parse_modifiers("cmd+shift")
    assert [m.flag for m in mods] == [FLAG_CMD, FLAG_SHIFT]


def test_parse_modifiers_rejects_non_modifier():
    with pytest.raises(KeyNameError, match="not a modifier"):
        parse_modifiers("cmd+a")
