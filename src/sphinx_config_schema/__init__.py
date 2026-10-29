"""Render a JSON schema as a copyable TOML, YAML, or JSON example in Sphinx."""

# cspell:ignore astext docname docnames doctree ensurenl refid relfn stripnl templatename

from __future__ import annotations

import html
import importlib.metadata
import itertools
import json
import re
from collections.abc import Sequence  # ruff: ignore[typing-only-standard-library-import] # autodoc resolves the annotations
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, cast

from docutils import nodes
from docutils.parsers.rst import directives
from pygments.lexers import get_lexer_by_name
from pygments.token import STANDARD_TYPES
from sphinx.directives.code import container_wrapper
from sphinx.util.docutils import SphinxDirective
from typing_extensions import override

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pygments.token import _TokenType
    from sphinx.application import Sphinx
    from sphinx.environment import BuildEnvironment

CSS_CLASS = "config-schema-key"
STATIC_DIR = Path(__file__).parent / "_static"


@dataclass(frozen=True)
class Setting:
    """One key-value pair in the generated example."""

    table: tuple[str, ...]
    name: str
    value: Any
    description: str
    anchor_suffix: str = field(default="", repr=False)
    """Distinguishes `.anchor` from that of the same key elsewhere on the page."""

    @property
    def path(self) -> tuple[str, ...]:
        return (*self.table, self.name)

    @property
    def anchor(self) -> str:
        return nodes.make_id(".".join(self.path) + self.anchor_suffix)


@dataclass(frozen=True)
class Table:
    """A nested table in the generated example, which holds settings of its own."""

    table: tuple[str, ...]
    name: str
    description: str
    anchor_suffix: str = field(default="", repr=False)

    @property
    def path(self) -> tuple[str, ...]:
        return (*self.table, self.name)

    @property
    def anchor(self) -> str:
        return nodes.make_id(".".join(self.path) + self.anchor_suffix)


Entry = Setting | Table
"""A key in the generated example."""


class ConfigSchemaDirective(SphinxDirective):
    """Render a copyable TOML, YAML, or JSON example from a JSON schema.

    Each key in the example is an anchor that sphinx-tippy turns into a tooltip with the
    description of that setting.
    """

    has_content = False
    required_arguments = 1
    option_spec = MappingProxyType({
        "caption": directives.unchanged_required,
        "format": lambda arg: directives.choice(arg, FORMATS),
        "strict": directives.flag,
        "table": directives.unchanged_required,
    })

    @override
    def run(self) -> list[nodes.Node]:
        rel_path, abs_path = self.env.relfn2path(self.arguments[0])
        self.env.note_dependency(rel_path)
        schema = json.loads(Path(abs_path).read_text())
        table = (
            tuple(self.options.get("table", "").split("."))
            if "table" in self.options
            else ()
        )
        fmt = self.options.get("format", "toml")
        strict = "strict" in self.options
        try:
            settings = list(iter_settings(schema, table=table, strict=strict))
        except ValueError as exc:
            raise self.error(str(exc)) from exc
        tips: dict[str, str] = _get_tips(self.env).setdefault(self.env.docname, {})
        settings = [_make_unique(s, fmt, tips) for s in _drop_empty_tables(settings)]
        tips.update({f"#{s.anchor}": to_tooltip(s.description) for s in settings})
        example: nodes.Node = create_literal_block(settings, fmt, rawsource=self.name)
        self.set_source_info(example)
        caption = self.options.get("caption")
        if caption is not None:
            example = container_wrapper(self, example, caption)
        return [example]


def _drop_empty_tables(entries: list[Entry]) -> list[Entry]:
    """Remove the tables that do not appear in the example, as no setting is in them."""
    used = {
        s.table[:i]
        for s in entries
        if isinstance(s, Setting)
        for i in range(len(s.table) + 1)
    }
    return [e for e in entries if isinstance(e, Setting) or e.path in used]


def _make_unique(setting: Entry, fmt: str, tips: dict[str, str]) -> Entry:
    """Suffix the anchor of a setting if an earlier example on the page already uses it.

    This happens when the same schema is shown in several formats, for instance in tabs.

    >>> tips = {"#port": "", "#port-yaml": ""}
    >>> _make_unique(Setting((), "port", 80, ""), "yaml", tips).anchor
    'port-yaml-2'
    """
    suffixes = itertools.chain(
        ("", f".{fmt}"), (f".{fmt}.{i}" for i in itertools.count(2))
    )
    candidates = (replace(setting, anchor_suffix=s) for s in suffixes)
    return next(c for c in candidates if f"#{c.anchor}" not in tips)


def iter_settings(
    schema: dict[str, Any], table: tuple[str, ...] = (), *, strict: bool = False
) -> Iterator[Entry]:
    """Collect the settings with a default or example value from a JSON schema.

    Settings without a usable value are skipped, or reported with a `ValueError` after
    all other settings have been collected if ``strict`` is set. Nested tables are
    yielded as a `Table`, so that their key can carry a description as well.

    >>> schema = {
    ...     "properties": {
    ...         "name": {"description": "Project name.", "examples": ["demo"]},
    ...         "optional": {"type": "string"},
    ...     }
    ... }
    >>> list(iter_settings(schema, table=("tool", "demo")))
    [Setting(table=('tool', 'demo'), name='name', value='demo', description='Project name.')]
    >>> list(iter_settings(schema, strict=True))
    Traceback (most recent call last):
        ...
    ValueError: Settings without a default or example: optional
    """
    missing: list[str] = []
    for sub_table, properties in _iter_tables(
        table, schema.get("properties", {}), schema
    ):
        for name, field_schema in properties.items():
            resolved = _resolve_ref(field_schema, schema)
            if _is_table(resolved):
                description = field_schema.get("description") or resolved.get(
                    "description", ""
                )
                yield Table(sub_table, name, description)
                continue
            value = _example_value(field_schema)
            if value is None:
                missing.append(".".join((*sub_table, name)))
                continue
            description = field_schema.get("description", "")
            yield Setting(sub_table, name, value, description)
    if strict and missing:
        msg = f"Settings without a default or example: {', '.join(missing)}"
        raise ValueError(msg)


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
    table: tuple[str, ...], properties: dict[str, Any], schema: dict[str, Any]
) -> Iterator[tuple[tuple[str, ...], dict[str, Any]]]:
    yield table, properties
    for name, field_schema in properties.items():
        resolved = _resolve_ref(field_schema, schema)
        if _is_table(resolved):
            yield from _iter_tables((*table, name), resolved["properties"], schema)


def _is_table(field_schema: dict[str, Any]) -> bool:
    return (
        field_schema.get("type", "object") == "object" and "properties" in field_schema
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


FORMATS = ("toml", "yaml", "json")
"""Formats in which the example can be rendered."""

Fragment = tuple[str, "Entry | None"]
"""A piece of the example text, with its `Entry` if the piece is a key."""


def render(settings: Sequence[Entry], fmt: str = "toml") -> str:
    """Render the example as plain text.

    >>> settings = [Setting(("tool", "demo"), "transport", "auto", "")]
    >>> print(render(settings))
    [tool.demo]
    transport = "auto"
    >>> print(render(settings, "yaml"))
    tool:
      demo:
        transport: auto
    """
    return "".join(text for text, _ in iter_fragments(settings, fmt))


def iter_fragments(settings: Sequence[Entry], fmt: str) -> Iterator[Fragment]:
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
) -> Iterator[Fragment]:
    table: tuple[str, ...] = ()
    first = True
    for setting in settings:
        if setting.table != table:
            if not first:
                yield "\n", None
            *parents, name = map(_to_toml_key, setting.table)
            yield "[" + "".join(f"{p}." for p in parents), None
            yield name, tables.get(setting.table)
            yield "]\n", None
            table = setting.table
        first = False
        yield _to_toml_key(setting.name), setting
        yield f" = {to_toml_value(setting.value)}\n", None


def _iter_yaml(
    tree: _Tree,
    tables: dict[tuple[str, ...], Table],
    path: tuple[str, ...],
    indent: str,
) -> Iterator[Fragment]:
    for key, child in tree.items():
        yield indent, None
        if isinstance(child, Setting):
            yield _to_yaml_key(key), child
            yield f": {to_yaml_value(child.value)}\n", None
        else:
            yield _to_yaml_key(key), tables.get((*path, key))
            yield ":\n", None
            yield from _iter_yaml(child, tables, (*path, key), indent + "  ")


def _iter_json(
    tree: _Tree,
    tables: dict[tuple[str, ...], Table],
    path: tuple[str, ...],
    indent: str,
) -> Iterator[Fragment]:
    if not tree:
        yield "{}", None
        return
    yield "{\n", None
    for i, (key, child) in enumerate(tree.items()):
        yield indent + "  ", None
        if isinstance(child, Setting):
            yield _to_json(key), child
            yield f": {_to_json(child.value)}", None
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


def create_literal_block(
    settings: Sequence[Entry], fmt: str, rawsource: str
) -> nodes.Element:
    """Build the example as a code block in which each key is an anchor.

    The anchor is what sphinx-tippy attaches the tooltip to; it refers to itself so that
    the key doubles as a permalink to the setting.

    The example is highlighted as a whole, so that the lexer sees the full context, and
    the tokens of each key are then wrapped in its anchor.

    Sphinx highlights a literal block again when its ``rawsource`` equals its text,
    which would drop the inline nodes built here. A ``rawsource`` that differs from the
    text, such as the directive name, marks the block as a parsed literal instead. The
    surrounding containers give the block the class names that themes and
    sphinx-copybutton expect from a regular code block.
    """
    fragments = list(iter_fragments(settings, fmt))
    tokens = _highlight("".join(text for text, _ in fragments), fmt)
    block = nodes.literal_block(rawsource, "")
    for text, setting in fragments:
        inlines = _take(tokens, len(text))
        if setting is None:
            block += inlines
            continue
        block += nodes.reference(
            "",
            "",
            *inlines,
            classes=[CSS_CLASS],
            ids=[setting.anchor],
            refid=setting.anchor,
        )
    highlight = nodes.container("", block, classes=["highlight"])
    return nodes.container("", highlight, classes=[f"highlight-{fmt}", "notranslate"])


def _take(tokens: list[nodes.inline], length: int) -> list[nodes.inline]:
    """Remove the first ``length`` characters from the tokens, splitting one if needed.

    >>> tokens = _highlight("port = 80", "toml")
    >>> [node.astext() for node in _take(tokens, 6)], tokens[0].astext()
    (['port', ' ', '='], ' ')
    """
    taken: list[nodes.inline] = []
    while length > 0:
        token = tokens.pop(0)
        text = token.astext()
        if len(text) > length:
            classes = token["classes"]
            tokens.insert(0, nodes.inline("", text[length:], classes=classes))
            token = nodes.inline("", text[:length], classes=classes)
            text = text[:length]
        taken.append(token)
        length -= len(text)
    return taken


def _highlight(source: str, fmt: str) -> list[nodes.inline]:
    r"""Tokenize source code into inline nodes that carry the CSS classes of Pygments.

    >>> [(node.astext(), node["classes"]) for node in _highlight("port = 80", "toml")]
    [('port', ['n']), (' ', ['w']), ('=', ['o']), (' ', ['w']), ('80', ['mi'])]
    """
    lexer = get_lexer_by_name(fmt, stripnl=False, ensurenl=False)
    return [
        nodes.inline(
            "", text, classes=[css_class] if (css_class := _css_class(t)) else []
        )
        for _, t, text in lexer.get_tokens_unprocessed(source)
        if text
    ]


def _css_class(token_type: _TokenType | None) -> str:
    """Look up the CSS class of a token type as the Pygments HTML formatter does.

    >>> from pygments import token
    >>> _css_class(token.Name), _css_class(token.String.Double)
    ('n', 's2')
    """
    while token_type is not None and token_type not in STANDARD_TYPES:
        token_type = token_type.parent
    return STANDARD_TYPES.get(token_type, "")


_LITERAL_PATTERN = re.compile(r"``(?P<text>[^`]+)``")


def to_tooltip(description: str) -> str:
    """Convert a schema description to the HTML shown in its tooltip.

    Only inline literals are supported, as that is the reStructuredText markup that
    descriptions generated from Python docstrings typically use.

    >>> to_tooltip("Arguments for ``pytest``, such as ``-n auto``.")
    '<p>Arguments for <code>pytest</code>, such as <code>-n auto</code>.</p>'
    """
    escaped = html.escape(description)
    body = _LITERAL_PATTERN.sub(r"<code>\g<text></code>", escaped)
    return f"<p>{body}</p>"


def _get_tips(env: BuildEnvironment) -> dict[str, dict[str, str]]:
    """Get the tooltips per document, which are stored in the build environment."""
    if not hasattr(env, "config_schema_tips"):
        env.config_schema_tips = {}  # ty: ignore[invalid-assignment]
    return env.config_schema_tips  # ty: ignore[unresolved-attribute]


def _purge_tips(_app: Sphinx, env: BuildEnvironment, docname: str) -> None:
    _get_tips(env).pop(docname, None)


def _merge_tips(
    _app: Sphinx, env: BuildEnvironment, docnames: set[str], other: BuildEnvironment
) -> None:
    other_tips = _get_tips(other)
    _get_tips(env).update({d: other_tips[d] for d in docnames if d in other_tips})


def _register_tips(
    app: Sphinx,
    pagename: str,
    _templatename: str,
    _context: dict[str, Any],
    _doctree: nodes.document | None,
) -> None:
    """Feed the tooltips to sphinx-tippy before it collects the tips of a page."""
    tips = _get_tips(app.env).get(pagename)
    if tips:
        app.env.tippy_config.custom_tips.update(tips)  # ty: ignore[unresolved-attribute]


def setup(app: Sphinx) -> dict[str, Any]:
    app.setup_extension("sphinx_tippy")
    app.add_directive("config-schema", ConfigSchemaDirective)
    app.connect("builder-inited", _add_static_path)
    app.connect("env-purge-doc", _purge_tips)
    app.connect("env-merge-info", _merge_tips)
    app.connect("html-page-context", _register_tips, priority=400)
    return {
        "parallel_read_safe": True,
        "parallel_write_safe": True,
        "version": importlib.metadata.version("sphinx-config-schema"),
    }


def _add_static_path(app: Sphinx) -> None:
    app.config.html_static_path.append(str(STATIC_DIR))
    app.add_css_file("config-schema.css")
