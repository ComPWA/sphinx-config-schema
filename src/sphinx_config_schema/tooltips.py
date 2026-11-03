"""Create the tooltips of the keys and hand them to sphinx-tippy."""

# cspell:ignore docname docnames doctree templatename

from __future__ import annotations

import html
import json
import re
from typing import TYPE_CHECKING, Any

from sphinx_config_schema.schema import NO_DEFAULT, Entry, Table

if TYPE_CHECKING:
    from collections.abc import Sequence

    from docutils import nodes
    from sphinx.application import Sphinx
    from sphinx.environment import BuildEnvironment

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


def _entry_tooltip(entry: Entry) -> str:
    """Create the tooltip of a key, with the values that the example does not show.

    When the value shown is an example itself, the remaining ones are "Other examples".

    The tooltip is empty if there is nothing to show, in which case the key gets none.

    >>> from sphinx_config_schema.schema import Setting
    >>> _entry_tooltip(Setting((), "mode", "a", "Mode.", allowed=("a", "b")))
    '<p>Mode.</p><p>Allowed values: <code>&quot;a&quot;</code>, <code>&quot;b&quot;</code></p>'
    >>> _entry_tooltip(Setting((), "port", 80, "", examples=(80, 8080)))
    '<p>Examples: <code>8080</code></p>'
    >>> _entry_tooltip(
    ...     Setting((), "port", 80, "", examples=(80, 8080), value_source="example")
    ... )
    '<p>Other examples: <code>8080</code></p>'
    >>> _entry_tooltip(Setting((), "host", "a", "Host.", required=True))
    '<p>Host.</p><p>Required</p>'
    >>> _entry_tooltip(Table((), "format", ""))
    ''
    """
    tooltip = to_tooltip(entry.description) if entry.description else ""
    if entry.required:
        tooltip += "<p>Required</p>"
    if isinstance(entry, Table):
        return tooltip
    if entry.default is not NO_DEFAULT:
        tooltip += f"<p>Default: {_code(entry.default)}</p>"
    if entry.allowed:
        tooltip += f"<p>Allowed values: {_code_list(entry.allowed)}</p>"
    examples = [e for e in entry.examples if e is not None and e != entry.value]
    if examples:
        label = "Other examples" if entry.value_source == "example" else "Examples"
        tooltip += f"<p>{label}: {_code_list(examples)}</p>"
    return tooltip


def _code_list(values: Sequence[Any]) -> str:
    return ", ".join(_code(v) for v in values)


def _code(value: Any) -> str:
    return f"<code>{html.escape(json.dumps(value))}</code>"


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
