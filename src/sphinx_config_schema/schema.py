"""Collect the settings of a JSON schema that the example shows."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from docutils import nodes
from typing_extensions import Sentinel

if TYPE_CHECKING:
    from collections.abc import Iterator


NO_DEFAULT = Sentinel("NO_DEFAULT")
"""Default of a `.Setting` whose schema has none, as `None` is a valid default.

:meta hide-value: true
"""


@dataclass(frozen=True)
class Setting:
    """One key-value pair in the generated example."""

    table: tuple[str, ...]
    """Keys of the enclosing tables, one per nesting level, such as ``("tool", "demo")`` for ``[tool.demo]``; empty at the top level."""
    name: str
    """Unquoted key of the setting within its table."""
    value: Any
    """Value shown in the example, which `.value_source` traces back to the schema."""
    description: str
    """Description from the schema for the tooltip, in which ``inline literals`` become code."""
    examples: tuple[Any, ...] = field(default=(), repr=False)
    """Example values from the schema, listed in the tooltip unless `.value` shows them."""
    allowed: tuple[Any, ...] = field(default=(), repr=False)
    """The values that the schema allows for this setting through ``enum``."""
    default: Any = field(default=NO_DEFAULT, repr=False)
    """The actual schema default, kept separate from the displayed example."""
    value_source: Literal["default", "example", "enum", "placeholder"] | None = field(
        default=None, repr=False
    )
    """Origin of `.value`; unset for settings constructed without schema metadata.

    A ``"placeholder"`` is the empty mapping shown for a free-form table, an object with
    ``additionalProperties`` but neither ``properties`` nor a value to show.
    """
    required: bool = field(default=False, repr=False)
    """Whether the enclosing object lists the key under ``required``."""
    _anchor_prefix: str = field(default="", repr=False)
    _anchor_suffix: str = field(default="", repr=False)

    @property
    def path(self) -> tuple[str, ...]:
        """Full path of the key, including its `.name`."""
        return (*self.table, self.name)

    @property
    def anchor(self) -> str:
        """HTML ID of the key, from which its :rst:role:`ref` label is formed."""
        return _make_anchor(self._anchor_prefix, self.path, self._anchor_suffix)


@dataclass(frozen=True)
class Table:
    """A nested table in the generated example, which holds settings of its own."""

    table: tuple[str, ...]
    """Keys of the enclosing tables, as in `.Setting.table`."""
    name: str
    """Unquoted key of the table within its parent."""
    description: str
    """Description from the schema for the tooltip, as in `.Setting.description`."""
    required: bool = field(default=False, repr=False)
    """Whether the enclosing object lists the table under ``required``."""
    _anchor_prefix: str = field(default="", repr=False)
    _anchor_suffix: str = field(default="", repr=False)

    @property
    def path(self) -> tuple[str, ...]:
        """Full path of the table, including its `.name`."""
        return (*self.table, self.name)

    @property
    def anchor(self) -> str:
        """HTML ID of the key, from which its :rst:role:`ref` label is formed."""
        return _make_anchor(self._anchor_prefix, self.path, self._anchor_suffix)


Entry = Setting | Table
"""A key in the generated example."""


def _make_anchor(prefix: str, path: tuple[str, ...], suffix: str) -> str:
    """Join the path components with dots, so that the hierarchy stays recognizable.

    >>> _make_anchor("settings", ("tool", "log_level"), "")
    'settings.tool.log-level'
    >>> _make_anchor("", ("tool", "port"), "-yaml-2")
    'tool.port-yaml-2'
    """
    components = (prefix, *path) if prefix else path
    return ".".join(nodes.make_id(c) for c in components) + suffix


def iter_settings(
    schema: dict[str, Any], table: tuple[str, ...] = (), *, strict: bool = False
) -> Iterator[Entry]:
    """Collect the settings with a default or example value from a JSON schema.

    Settings without a usable value are skipped, or reported with a `ValueError` after
    all other settings have been collected if ``strict`` is set. Nested tables are
    yielded as a `Table`, so that their key can carry a description as well. So is the
    last part of ``table``, with the description of the schema itself.

    >>> schema = {
    ...     "description": "Demo settings.",
    ...     "properties": {
    ...         "name": {"description": "Project name.", "examples": ["demo"]},
    ...         "optional": {"type": "string"},
    ...     },
    ... }
    >>> for entry in iter_settings(schema, table=("tool", "demo")):
    ...     print(entry)
    Table(table=('tool',), name='demo', description='Demo settings.')
    Setting(table=('tool', 'demo'), name='name', value='demo', description='Project name.')
    >>> list(iter_settings(schema, strict=True))
    Traceback (most recent call last):
        ...
    ValueError: Settings without a default or example: optional
    """
    missing: list[str] = []
    if table:
        yield Table(table[:-1], table[-1], schema.get("description", ""))
    for sub_table, obj in _iter_tables(table, schema, schema):
        required = set(obj.get("required", ()))
        for name, field_schema in obj.get("properties", {}).items():
            resolved = _resolve_ref(field_schema, schema)
            if _is_table(resolved):
                description = field_schema.get("description") or resolved.get(
                    "description", ""
                )
                yield Table(sub_table, name, description, required=name in required)
                continue
            allowed = _enum_values(field_schema, schema)
            effective_schema = {**resolved, **field_schema}
            default = effective_schema.get("default", NO_DEFAULT)
            value = _example_value(effective_schema)
            value_source = "default" if value == default else "example"
            if value is None:
                value = next((item for item in allowed if item is not None), None)
                value_source = "enum"
            if value is None and _is_free_form_table(effective_schema):
                value = {}
                value_source = "placeholder"
            if value is None:
                missing.append(".".join((*sub_table, name)))
                continue
            yield Setting(
                sub_table,
                name,
                value,
                description=field_schema.get(
                    "description", resolved.get("description", "")
                ),
                examples=tuple(
                    field_schema.get("examples", resolved.get("examples", []))
                ),
                allowed=allowed,
                default=default,
                value_source=value_source,
                required=name in required,
            )
    if strict and missing:
        msg = f"Settings without a default or example: {', '.join(missing)}"
        raise ValueError(msg)


def _enum_values(
    field_schema: dict[str, Any],
    schema: dict[str, Any],
    seen: frozenset[int] = frozenset(),
) -> tuple[Any, ...]:
    """Collect enum choices from alternatives and local references without following cycles.

    An alternative without choices accepts other values too, so then there are none.

    >>> schema = {"$defs": {"Mode": {"enum": ["a", "b"]}}}
    >>> _enum_values({"anyOf": [{"$ref": "#/$defs/Mode"}, {"type": "null"}]}, schema)
    ('a', 'b', None)
    >>> _enum_values({"oneOf": [{"enum": ["a", "b"]}, {"enum": ["c"]}]}, {})
    ('a', 'b', 'c')
    >>> _enum_values({"anyOf": [{"type": "boolean"}, {"type": "null"}]}, {})
    ()
    >>> recursive = {"$defs": {"Mode": {"$ref": "#/$defs/Mode"}}}
    >>> _enum_values({"$ref": "#/$defs/Mode"}, recursive)
    ()
    """
    if id(field_schema) in seen:
        return ()
    seen |= {id(field_schema)}
    if "enum" in field_schema:
        return tuple(field_schema["enum"])
    resolved = _resolve_ref(field_schema, schema)
    if resolved is not field_schema:
        return _enum_values(resolved, schema, seen)
    if field_schema.get("type") == "null":
        return (None,)
    values: list[Any] = []
    for alternative in field_schema.get("anyOf", field_schema.get("oneOf", [])):
        choices = _enum_values(alternative, schema, seen)
        if not choices:
            return ()
        values.extend(v for v in choices if v not in values)
    return tuple(values)


def _example_value(field_schema: dict[str, Any]) -> Any:
    """Select the value shown for a setting: its default, or else its first example.

    An empty collection is a placeholder rather than a meaningful default, so it gives
    way to an example when the setting declares one.

    >>> _example_value({"default": [], "examples": [["pc15"]]})
    ['pc15']
    >>> _example_value({"default": [], "examples": [None]})
    []
    """
    default = field_schema.get("default")
    if default is not None and not (isinstance(default, list | dict) and not default):
        return default
    examples = [e for e in field_schema.get("examples", []) if e is not None]
    if examples:
        return examples[0]
    return default


def _iter_tables(
    table: tuple[str, ...], obj: dict[str, Any], schema: dict[str, Any]
) -> Iterator[tuple[tuple[str, ...], dict[str, Any]]]:
    """Yield the path and schema of an object and of every object nested in it."""
    yield table, obj
    for name, field_schema in obj.get("properties", {}).items():
        resolved = _resolve_ref(field_schema, schema)
        if _is_table(resolved):
            yield from _iter_tables((*table, name), resolved, schema)


def _is_table(field_schema: dict[str, Any]) -> bool:
    return (
        field_schema.get("type", "object") == "object" and "properties" in field_schema
    )


def _is_free_form_table(field_schema: dict[str, Any]) -> bool:
    """Check whether a field is a table of arbitrary keys, such as environment variables.

    >>> _is_free_form_table({
    ...     "type": "object",
    ...     "additionalProperties": {"type": "string"},
    ... })
    True
    >>> _is_free_form_table({"type": "object", "additionalProperties": False})
    False
    """
    return (
        field_schema.get("type") == "object"
        and field_schema.get("additionalProperties", True) is not False
        and "properties" not in field_schema
    )


def _resolve_ref(
    field_schema: dict[str, Any], schema: dict[str, Any]
) -> dict[str, Any]:
    """Follow a local ``$ref``, such as the ``#/$defs/...`` references of pydantic.

    >>> schema = {"$defs": {"Paths": {"properties": {}}}}
    >>> _resolve_ref({"$ref": "#/$defs/Paths"}, schema)
    {'properties': {}}
    """
    reference = field_schema.get("$ref")
    if reference is None or not reference.startswith("#/"):
        return field_schema
    resolved: Any = schema
    for part in reference.removeprefix("#/").split("/"):
        resolved = resolved[part]
    return resolved
