"""Render the settings as TOML, YAML, or JSON text."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence  # ruff: ignore[typing-only-standard-library-import] # autodoc resolves the annotations
from typing import TYPE_CHECKING, Any, cast

from sphinx_config_schema.schema import Setting, Table

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sphinx_config_schema.schema import Entry

FORMATS = ("toml", "yaml", "json")
"""Formats in which the example can be rendered."""

_Fragment = tuple[str, "Entry | None"]
"""A piece of the example text, with its `.Entry` if the piece is a key."""


def render(settings: Sequence[Entry], fmt: str = "toml") -> str:
    """Render the example as plain text.

    >>> from sphinx_config_schema.schema import Setting
    >>> settings = [Setting(("tool", "demo"), "transport", "auto", "")]
    >>> print(render(settings))
    [tool.demo]
    transport = "auto"
    >>> print(render(settings, "yaml"))
    tool:
      demo:
        transport: auto
    """
    return "".join(text for text, _ in _iter_fragments(settings, fmt))


def _iter_fragments(settings: Sequence[Entry], fmt: str) -> Iterator[_Fragment]:
    """Split the example text into its keys and the text in between."""
    leaves = [s for s in settings if isinstance(s, Setting)]
    tables = {s.path: s for s in settings if isinstance(s, Table)}
    if fmt == "toml":
        fragments = list(_iter_toml(leaves, tables))
    elif fmt == "yaml":
        fragments = list(_iter_yaml(_build_tree(leaves), tables, (), indent=""))
    elif fmt == "json":
        fragments = list(_iter_json(_build_tree(leaves), tables, (), indent=""))
    else:
        msg = f"Unknown format {fmt!r}, choose from {', '.join(FORMATS)}"
        raise ValueError(msg)
    if fragments:
        text, setting = fragments.pop()
        fragments.append((text.rstrip("\n"), setting))
    yield from fragments


_Tree = dict[str, "Setting | _Tree"]


def _build_tree(settings: list[Setting]) -> _Tree:
    """Nest the settings by their table, keeping the order in which they appear."""
    tree: _Tree = {}
    for setting in settings:
        node = tree
        for part in setting.table:
            node = cast("_Tree", node.setdefault(part, {}))
        node[setting.name] = setting
    return tree


def _iter_toml(
    settings: list[Setting], tables: dict[tuple[str, ...], Table]
) -> Iterator[_Fragment]:
    """Write the settings under table headers, anchoring each table at its first header.

    A table without settings of its own has no header, so it is anchored in the first
    header of its subtables, such as ``pwa`` in ``[tool.pwa.paths]``.
    """
    table: tuple[str, ...] = ()
    anchored: set[tuple[str, ...]] = set()
    first = True
    for setting in settings:
        if setting.table != table:
            if not first:
                yield "\n", None
            yield "[", None
            for depth in range(1, len(setting.table) + 1):
                path = setting.table[:depth]
                entry = None if path in anchored else tables.get(path)
                anchored.add(path)
                if depth > 1:
                    yield ".", None
                yield _to_toml_key(path[-1]), entry
            yield "]\n", None
            table = setting.table
        first = False
        if setting.default is None:
            yield "# ", None
        yield _to_toml_key(setting.name), setting
        yield f" = {to_toml_value(setting.value)}\n", None


def _iter_yaml(
    tree: _Tree,
    tables: dict[tuple[str, ...], Table],
    path: tuple[str, ...],
    indent: str,
) -> Iterator[_Fragment]:
    for key, child in tree.items():
        yield indent, None
        if isinstance(child, Setting):
            yield _to_yaml_key(key), child
            yield (
                f": {to_yaml_value(None if child.default is None else child.value)}\n",
                None,
            )
        else:
            yield _to_yaml_key(key), tables.get((*path, key))
            yield ":\n", None
            yield from _iter_yaml(child, tables, (*path, key), indent + "  ")


def _iter_json(
    tree: _Tree,
    tables: dict[tuple[str, ...], Table],
    path: tuple[str, ...],
    indent: str,
) -> Iterator[_Fragment]:
    if not tree:
        yield "{}", None
        return
    yield "{\n", None
    for i, (key, child) in enumerate(tree.items()):
        yield indent + "  ", None
        if isinstance(child, Setting):
            yield _to_json(key), child
            yield f": {_to_json(None if child.default is None else child.value)}", None
        else:
            yield _to_json(key), tables.get((*path, key))
            yield ": ", None
            yield from _iter_json(child, tables, (*path, key), indent + "  ")
        yield ",\n" if i < len(tree) - 1 else "\n", None
    yield indent + "}", None


def to_toml_value(value: Any) -> str:
    """Render a JSON value as an inline TOML value.

    >>> to_toml_value({"name": "demo", "paths": ["a", "b"], "strict": True})
    '{ name = "demo", paths = ["a", "b"], strict = true }'
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return repr(value)
    if isinstance(value, str):
        return _to_json(value)
    if isinstance(value, list):
        return "[" + ", ".join(to_toml_value(v) for v in value) + "]"
    if isinstance(value, dict):
        if not value:
            return "{}"
        items = ", ".join(
            f"{_to_toml_key(k)} = {to_toml_value(v)}" for k, v in value.items()
        )
        return f"{{ {items} }}"
    msg = f"Cannot render {value!r} as a TOML value"
    raise TypeError(msg)


def to_yaml_value(value: Any) -> str:
    """Render a JSON value as a YAML flow value.

    >>> to_yaml_value({"name": "demo", "paths": ["a", "b"], "strict": True, "v": "1.0"})
    '{name: demo, paths: [a, b], strict: true, v: "1.0"}'
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return repr(value)
    if isinstance(value, str):
        return _to_yaml_key(value)
    if isinstance(value, list):
        return "[" + ", ".join(to_yaml_value(v) for v in value) + "]"
    if isinstance(value, dict):
        items = ", ".join(
            f"{_to_yaml_key(k)}: {to_yaml_value(v)}" for k, v in value.items()
        )
        return f"{{{items}}}"
    msg = f"Cannot render {value!r} as a YAML value"
    raise TypeError(msg)


def _to_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False)
    except TypeError as exc:
        msg = f"Cannot render {value!r} as a JSON value"
        raise TypeError(msg) from exc


_BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")


def _to_toml_key(key: str) -> str:
    """Quote a key if it is not a valid bare TOML key.

    >>> _to_toml_key("web-root"), _to_toml_key("web.example.edu")
    ('web-root', '"web.example.edu"')
    """
    if _BARE_KEY.match(key):
        return key
    return _to_json(key)


_PLAIN_YAML = re.compile(r"^[A-Za-z_][A-Za-z0-9_.\-/]*$")
_YAML_KEYWORDS = frozenset({
    "true",
    "false",
    "yes",
    "no",
    "on",
    "off",
    "null",
    "y",
    "n",
})


def _to_yaml_key(text: str) -> str:
    """Quote a string unless YAML reads it unquoted as the same string.

    >>> _to_yaml_key("web.example.edu"), _to_yaml_key("no"), _to_yaml_key("a b")
    ('web.example.edu', '"no"', '"a b"')
    """
    if _PLAIN_YAML.match(text) and text.lower() not in _YAML_KEYWORDS:
        return text
    return _to_json(text)
