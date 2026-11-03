"""Build the example as a highlighted code block in which each key is an anchor."""

# cspell:ignore astext commandchars curfilestack ensurenl hypertarget refid sphinxalltt sphinxsamedocref stripnl

from __future__ import annotations

from collections.abc import Sequence  # ruff: ignore[typing-only-standard-library-import] # autodoc resolves the annotations
from typing import TYPE_CHECKING

from docutils import nodes
from pygments.formatters.latex import escape_tex
from pygments.lexers import get_lexer_by_name
from pygments.token import STANDARD_TYPES

from sphinx_config_schema.render import _iter_fragments

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pygments.token import _TokenType
    from sphinx.writers.latex import LaTeXTranslator

    from sphinx_config_schema.schema import Entry

CSS_CLASS = "config-schema-key"
REQUIRED_CSS_CLASS = "config-schema-required"


def create_literal_block(
    settings: Sequence[Entry], fmt: str, rawsource: str
) -> nodes.Element:
    """Build the example as a code block in which each key is an anchor.

    The anchor is what sphinx-tippy attaches the tooltip to; it refers to itself so that
    the key doubles as a permalink to the setting.

    The example is highlighted as a whole, so that the lexer sees the full context, and
    the tokens of each key are then wrapped in its anchor.

    Sphinx highlights a literal block again when its `~docutils.nodes.Element.rawsource`
    equals its text, which would drop the inline nodes built here. A
    `~docutils.nodes.Element.rawsource` that differs from the text, such as the
    directive name, marks the block as a parsed literal instead. The surrounding
    containers give the block the class names that themes and sphinx-copybutton expect
    from a regular code block.
    """
    fragments = list(_iter_fragments(settings, fmt))
    tokens = _highlight("".join(text for text, _ in fragments), fmt)
    block = _example_block(rawsource, "")
    block["comment"] = _COMMENT_PREFIXES.get(fmt)
    for text, setting in fragments:
        inlines = _take(tokens, len(text))
        if setting is None:
            block += inlines
            continue
        block += nodes.reference(
            "",
            "",
            *inlines,
            classes=[CSS_CLASS, REQUIRED_CSS_CLASS]
            if setting.required
            else [CSS_CLASS],
            ids=[setting.anchor],
            refid=setting.anchor,
        )
    highlight = nodes.container("", block, classes=["highlight"])
    return nodes.container("", highlight, classes=[f"highlight-{fmt}", "notranslate"])


_COMMENT_PREFIXES = {"toml": "#", "yaml": "#"}
"""Line comment syntax of the formats that have one, to mark required keys in LaTeX."""


class _example_block(nodes.literal_block):  # ruff: ignore[invalid-class-name]
    """Literal block of an example, which LaTeX renders as a highlighted code block.

    Other builders handle it as the parsed literal that it is otherwise.
    """


def _visit_example_block_latex(self: LaTeXTranslator, node: _example_block) -> None:
    r"""Write the example as a ``sphinxVerbatim`` block with Pygments macros.

    The LaTeX writer renders a parsed literal as plain ``sphinxalltt``, which has no
    frame, caption, or highlighting. Sphinx defines the ``\PYG`` macros used here for
    its own code blocks.

    Output without CSS cannot show the marker of required keys, so the line of a
    required key ends in a ``# required`` comment instead, in formats that have
    comments.
    """
    body = "".join(_mark_required(_latex_tokens(self, node), node))
    self.body.append(
        "\n"
        Rf"\begin{{sphinxVerbatim}}[commandchars=\\\{{\}}]"
        f"\n{body}\n"
        Rf"\end{{sphinxVerbatim}}"
        "\n"
    )
    raise nodes.SkipNode


def _mark_required(
    tokens: Iterator[tuple[str, bool]], node: nodes.Element
) -> Iterator[str]:
    r"""End the line of each required key in a comment, if the format has comments.

    >>> node = _example_block("", "")
    >>> node["comment"] = "#"
    >>> tokens = [("key", True), (" = 1\nother", False), (" = 2", True)]
    >>> print("".join(_mark_required(iter(tokens), node)))
    key = 1\PYG{c+c1}{  \PYGZsh{} required}
    other = 2\PYG{c+c1}{  \PYGZsh{} required}
    """
    prefix = node.get("comment")
    comment = _latex_token(f"  {prefix} required", ["c1"]) if prefix else ""
    pending = False
    for text, required in tokens:
        if pending and "\n" in text:
            head, tail = text.split("\n", 1)
            yield f"{head}{comment}\n{tail}"
            pending = False
        else:
            yield text
        pending = pending or (required and bool(comment))
    if pending:
        yield comment


def _latex_tokens(
    self: LaTeXTranslator, node: nodes.Element
) -> Iterator[tuple[str, bool]]:
    """Yield the LaTeX of each top-level token and whether it is a required key."""
    for child in node.children:
        if isinstance(child, nodes.reference):
            refid = f"{self.curfilestack[-1]}:{child['refid']}"
            label = "".join(self.hypertarget(i) for i in child["ids"])
            inner = "".join(text for text, _ in _latex_tokens(self, child))
            required = REQUIRED_CSS_CLASS in child["classes"]
            yield (
                Rf"{label}{self.hyperlink(refid)}\sphinxsamedocref{{{inner}}}}}}}",
                required,
            )
        elif isinstance(child, nodes.inline):
            yield _latex_token(child.astext(), child["classes"]), False


def _latex_token(text: str, classes: list[str]) -> str:
    r"""Escape a token and wrap it in the ``\PYG`` macro of its Pygments style.

    >>> _latex_token('"a{b}"', ["s2"])
    '\\PYG{l+s+s2}{\\PYGZdq{}a\\PYGZob{}b\\PYGZcb{}\\PYGZdq{}}'
    """
    text = escape_tex(text, "PYG")
    if not classes:
        return text
    style = _latex_style(classes[0])
    return "\n".join(
        Rf"\PYG{{{style}}}{{{line}}}" if line else "" for line in text.split("\n")
    )


def _latex_style(css_class: str) -> str:
    r"""Name the ``\PYG`` style of a CSS class as the Pygments LaTeX formatter does.

    >>> _latex_style("s2"), _latex_style("n")
    ('l+s+s2', 'n')
    """
    token_type = _CSS_TOKEN_TYPES[css_class]
    names = []
    while token_type.parent is not None:
        names.append(STANDARD_TYPES[token_type])
        token_type = token_type.parent
    return "+".join(reversed(names))


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


_CSS_TOKEN_TYPES = {
    css: token_type for token_type, css in STANDARD_TYPES.items() if css
}


def _css_class(token_type: _TokenType | None) -> str:
    """Look up the CSS class of a token type as the Pygments HTML formatter does.

    >>> from pygments import token
    >>> _css_class(token.Name), _css_class(token.String.Double)
    ('n', 's2')
    """
    while token_type is not None and token_type not in STANDARD_TYPES:
        token_type = token_type.parent
    return STANDARD_TYPES.get(token_type, "")
