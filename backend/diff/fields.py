"""Generic field-by-field comparison of two entities.

Works on the plain dicts that model_dump() produces, so it covers every
field the parser has today and every field it gains later. Lists whose
elements all carry a unique "name" are matched by name, never by position.
The exception is the lists where position itself is meaning (UDT members,
AOI parameters): those additionally report a reorder as one order change.
"""
from __future__ import annotations

from .models import FieldChange


def diff_fields(
    old: dict,
    new: dict,
    exclude: frozenset[str] = frozenset(),
    prefix: str = "",
) -> list[FieldChange]:
    """List the paths where two model dumps differ.

    `exclude` skips top-level keys of these dicts (e.g. "content" on a
    routine, "export_date" on metadata). `prefix` is prepended to every
    path, e.g. "controller".
    """
    changes: list[FieldChange] = []
    for key in _ordered_keys(old, new):
        if key in exclude:
            continue
        _walk(old.get(key), new.get(key), _join(prefix, key), changes)
    return changes


def _ordered_keys(old: dict, new: dict) -> list:
    """Old's keys in order, then any keys only new has."""
    return [*old, *(k for k in new if k not in old)]


def _join(prefix: str, key: str) -> str:
    return f"{prefix}.{key}" if prefix else str(key)


# Keys that identify an element of a list, tried in this order. Most lists
# use "name"; module ports use "id"; controller ethernet ports use "port".
_IDENTITY_KEYS = ("name", "id", "port")

# Named lists that are real sequences, not bags of named things: UDT member
# order is the structure's memory layout, AOI parameter order is the operand
# order at every call site. A reorder inside these lists is a real change and
# is reported; every other named list stays order-free, because there export
# position carries no meaning and reporting it would only be churn.
_ORDER_MATTERS = frozenset({"members", "parameters"})


def _named(items: object) -> dict | None:
    """Work out whether a list can be matched element-by-element by identity.

    Tags, members, modules and the like each carry a name (or port/id) that
    identifies them, so their lists should be compared per element — "tag X
    changed" — instead of as one big value. Returns {identity: element} when
    every element has the same identity key and no two share a value;
    returns None when the list has no usable identity, in which case the
    caller treats the whole list as a single value.
    """
    if not isinstance(items, list) or not items:
        return None
    if not all(isinstance(item, dict) for item in items):
        return None
    for key in _IDENTITY_KEYS:
        if all(key in item for item in items):
            by_key = {item[key]: item for item in items}
            if len(by_key) == len(items):
                return by_key
            return None
    return None


def _walk(old: object, new: object, path: str, out: list[FieldChange]) -> None:
    """Compare two values and record where they differ.

    Dicts are walked key by key, lists of named things element by element,
    and everything else that differs becomes one FieldChange at this path.
    """
    if old == new:
        return

    if isinstance(old, dict) and isinstance(new, dict):
        for key in _ordered_keys(old, new):
            _walk(old.get(key), new.get(key), _join(path, key), out)
        return

    old_named, new_named = _named(old), _named(new)
    if old_named is not None and new_named is not None:
        if path in _ORDER_MATTERS:
            _order_change(old_named, new_named, path, out)
        for name in _ordered_keys(old_named, new_named):
            old_item = old_named.get(name)
            new_item = new_named.get(name)
            if old_item is None or new_item is None:
                out.append(FieldChange(path=f"{path}[{name}]", old=old_item, new=new_item))
            else:
                _walk(old_item, new_item, f"{path}[{name}]", out)
        return

    out.append(FieldChange(path=path, old=old, new=new))


def _order_change(old_named: dict, new_named: dict, path: str, out: list[FieldChange]) -> None:
    """Report a reorder of the elements present on both sides.

    An addition or removal on its own is not a reorder — it already has its
    per-element change — so only the surviving elements' relative order is
    compared. The reported values are the full identity sequences, so the
    reader sees where any added element landed.
    """
    common = old_named.keys() & new_named.keys()
    if [k for k in old_named if k in common] != [k for k in new_named if k in common]:
        out.append(FieldChange(path=f"{path}.order", old=list(old_named), new=list(new_named)))
