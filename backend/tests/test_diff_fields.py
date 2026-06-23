"""Generic field differ: paths, nesting, name-keyed lists, exclusions."""
from diff.fields import diff_fields


def _paths(changes):
    return [(c.path, c.old, c.new) for c in changes]


def test_equal_dicts_no_changes():
    assert diff_fields({"a": 1, "b": "x"}, {"a": 1, "b": "x"}) == []


def test_scalar_change():
    assert _paths(diff_fields({"a": 1}, {"a": 2})) == [("a", 1, 2)]


def test_nested_dict_path():
    old = {"values": {"Cmd": {"PRE": "500"}}}
    new = {"values": {"Cmd": {"PRE": "750"}}}
    assert _paths(diff_fields(old, new)) == [("values.Cmd.PRE", "500", "750")]


def test_dict_key_added_and_removed():
    old = {"values": {"OnlyOld": "1", "Kept": "2"}}
    new = {"values": {"Kept": "2", "OnlyNew": "3"}}
    assert _paths(diff_fields(old, new)) == [
        ("values.OnlyOld", "1", None),
        ("values.OnlyNew", None, "3"),
    ]


def test_plain_list_is_a_leaf():
    assert _paths(diff_fields({"dims": [4]}, {"dims": [8]})) == [("dims", [4], [8])]


def test_named_list_matched_by_name():
    old = {"members": [{"name": "P1", "data_type": "DINT"}, {"name": "P2", "data_type": "REAL"}]}
    new = {"members": [{"name": "P2", "data_type": "REAL"}, {"name": "P1", "data_type": "REAL"}]}
    # P1 changed type; P2 only moved position, which is not a change
    assert _paths(diff_fields(old, new)) == [("members[P1].data_type", "DINT", "REAL")]


def test_named_list_add_remove():
    old = {"members": [{"name": "Gone", "data_type": "DINT"}]}
    new = {"members": [{"name": "Fresh", "data_type": "BOOL"}]}
    changes = _paths(diff_fields(old, new))
    assert ("members[Gone]", {"name": "Gone", "data_type": "DINT"}, None) in changes
    assert ("members[Fresh]", None, {"name": "Fresh", "data_type": "BOOL"}) in changes


def test_port_keyed_list_matched_by_port():
    # Controller ethernet ports have no "name"; their identity is "port"
    old = {"ethernet_ports": [{"port": 1, "port_enabled": True}, {"port": 2, "port_enabled": True}]}
    new = {"ethernet_ports": [{"port": 1, "port_enabled": False}, {"port": 2, "port_enabled": True}]}
    assert _paths(diff_fields(old, new)) == [("ethernet_ports[1].port_enabled", True, False)]


def test_exclude_skips_top_level_key():
    old = {"export_date": "Mon", "name": "A"}
    new = {"export_date": "Tue", "name": "A"}
    assert diff_fields(old, new, exclude=frozenset({"export_date"})) == []


def test_prefix_prepends():
    assert _paths(diff_fields({"name": "A"}, {"name": "B"}, prefix="controller")) == [
        ("controller.name", "A", "B")
    ]
