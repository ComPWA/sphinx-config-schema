"""Render a JSON schema as a copyable TOML example with tooltips in Sphinx."""

# cspell:ignore astext docname docnames doctree ensurenl refid relfn stripnl templatename

from __future__ import annotations

import html
import importlib.metadata
import json
import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

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

CSS_CLASS = "toml-schema-key"
STATIC_DIR = Path(__file__).parent / "_static"


@dataclass(frozen=True)
class Setting:
    """One key-value pair in the generated TOML example."""

    table: str
    name: str
    value: Any
    description: str

    @property
    def anchor(self) -> str:
        path = f"{self.table}.{self.name}" if self.table else self.name
        return nodes.make_id(path)


class TomlSchemaDirective(SphinxDirective):
    """Render a copyable TOML example from a JSON schema.

    Each key in the example is an anchor that sphinx-tippy turns into a tooltip with the
    description of that setting.
    """

    has_content = False
    required_arguments = 1
    option_spec = MappingProxyType({
        "caption": directives.unchanged_required,
        "strict": directives.flag,
        "table": directives.unchanged_required,
    })

    @override
    def run(self) -> list[nodes.Node]:
        rel_path, abs_path = self.env.relfn2path(self.arguments[0])
        self.env.note_dependency(rel_path)
        schema = json.loads(Path(abs_path).read_text())
        table = self.options.get("table", "")
        strict = "strict" in self.options
        try:
            settings = list(iter_settings(schema, table=table, strict=strict))
        except ValueError as exc:
            raise self.error(str(exc)) from exc
        tips: dict[str, str] = _get_tips(self.env).setdefault(self.env.docname, {})
        tips.update({f"#{s.anchor}": to_tooltip(s.description) for s in settings})
        example: nodes.Node = create_literal_block(settings, rawsource=self.name)
        self.set_source_info(example)
        caption = self.options.get("caption")
        if caption is not None:
            example = container_wrapper(self, example, caption)
        return [example]


def iter_settings(
    schema: dict[str, Any], table: str = "", *, strict: bool = False
) -> Iterator[Setting]:
    """Collect the settings with a default or example value from a JSON schema.

    Settings without a usable value are skipped, or reported with a `ValueError` after
    all other settings have been collected if ``strict`` is set.

    >>> schema = {
    ...     "properties": {
    ...         "name": {"description": "Project name.", "examples": ["demo"]},
    ...         "optional": {"type": "string"},
    ...     }
    ... }
    >>> list(iter_settings(schema, table="tool.demo"))
    [Setting(table='tool.demo', name='name', value='demo', description='Project name.')]
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
            if _is_table(_resolve_ref(field_schema, schema)):
                continue
            value = _example_value(field_schema)
            if value is None:
                missing.append(f"{sub_table}.{name}" if sub_table else name)
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
    table: str, properties: dict[str, Any], schema: dict[str, Any]
) -> Iterator[tuple[str, dict[str, Any]]]:
    yield table, properties
    for name, field_schema in properties.items():
        resolved = _resolve_ref(field_schema, schema)
        if _is_table(resolved):
            sub_table = f"{table}.{_to_toml_key(name)}" if table else _to_toml_key(name)
            yield from _iter_tables(sub_table, resolved["properties"], schema)


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


def render_toml(settings: list[Setting]) -> str:
    """Render the TOML example as plain text.

    >>> print(render_toml([Setting("tool.demo", "transport", "auto", "")]))
    [tool.demo]
    transport = "auto"
    """
    return "".join(text for text, _ in _iter_lines(settings)).rstrip("\n")


def _iter_lines(settings: list[Setting]) -> Iterator[tuple[str, Setting | None]]:
    """Yield the lines of the TOML example with the setting that each line defines."""
    table = ""
    first = True
    for setting in settings:
        if setting.table != table:
            if not first:
                yield "\n", None
            yield f"[{setting.table}]\n", None
            table = setting.table
        first = False
        yield (
            f"{_to_toml_key(setting.name)} = {to_toml_value(setting.value)}\n",
            setting,
        )


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
        return json.dumps(value, ensure_ascii=False)
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


_BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")


def _to_toml_key(key: str) -> str:
    """Quote a key if it is not a valid bare TOML key.

    >>> _to_toml_key("web-root"), _to_toml_key("web.example.edu")
    ('web-root', '"web.example.edu"')
    """
    if _BARE_KEY.match(key):
        return key
    return json.dumps(key, ensure_ascii=False)


def create_literal_block(settings: list[Setting], rawsource: str) -> nodes.Element:
    """Build the TOML example as a code block in which each key is an anchor.

    The anchor is what sphinx-tippy attaches the tooltip to; it refers to itself so that
    the key doubles as a permalink to the setting.

    Sphinx highlights a literal block again when its ``rawsource`` equals its text,
    which would drop the inline nodes built here. A ``rawsource`` that differs from the
    text, such as the directive name, marks the block as a parsed literal instead. The
    surrounding containers give the block the class names that themes and
    sphinx-copybutton expect from a regular code block.
    """
    block = nodes.literal_block(rawsource, "")
    for line, setting in _iter_lines(settings):
        if setting is None:
            block += _highlight(line)
            continue
        key = _to_toml_key(setting.name)
        block += nodes.reference(
            "",
            "",
            *_highlight(key, strip_newline=True),
            classes=[CSS_CLASS],
            ids=[setting.anchor],
            refid=setting.anchor,
        )
        block += _highlight(line.removeprefix(key))
    if block.children and block[-1].astext() == "\n":
        block.pop()
    highlight = nodes.container("", block, classes=["highlight"])
    return nodes.container("", highlight, classes=["highlight-toml", "notranslate"])


def _highlight(source: str, *, strip_newline: bool = False) -> list[nodes.Node]:
    r"""Tokenize TOML source into inline nodes that carry the CSS classes of Pygments.

    >>> [(node.astext(), node["classes"]) for node in _highlight("port = 80")]
    [('port', ['n']), (' ', ['w']), ('=', ['o']), (' ', ['w']), ('80', ['mi']), ('\n', ['w'])]
    """
    lexer = get_lexer_by_name("toml", stripnl=False, ensurenl=not strip_newline)
    return [
        nodes.inline(
            "", text, classes=[css_class] if (css_class := _css_class(t)) else []
        )
        for t, text in lexer.get_tokens(source)
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
    if not hasattr(env, "toml_schema_tips"):
        env.toml_schema_tips = {}  # ty: ignore[invalid-assignment]
    return env.toml_schema_tips  # ty: ignore[unresolved-attribute]


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
    app.add_directive("toml-schema", TomlSchemaDirective)
    app.connect("builder-inited", _add_static_path)
    app.connect("env-purge-doc", _purge_tips)
    app.connect("env-merge-info", _merge_tips)
    app.connect("html-page-context", _register_tips, priority=400)
    return {
        "parallel_read_safe": True,
        "parallel_write_safe": True,
        "version": importlib.metadata.version("sphinx-toml-schema"),
    }


def _add_static_path(app: Sphinx) -> None:
    app.config.html_static_path.append(str(STATIC_DIR))
    app.add_css_file("toml-schema.css")
