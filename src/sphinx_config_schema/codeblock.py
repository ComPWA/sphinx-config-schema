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
    fragments = list(_iter_fragments(settings, fmt))
    tokens = _highlight("".join(text for text, _ in fragments), fmt)
    block = _example_block(rawsource, "")
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


class _example_block(nodes.literal_block):  # ruff: ignore[invalid-class-name]
    """Literal block of an example, which LaTeX renders as a highlighted code block.

    Other builders handle it as the parsed literal that it is otherwise.
    """


def _visit_example_block_latex(self: LaTeXTranslator, node: _example_block) -> None:
    r"""Write the example as a ``sphinxVerbatim`` block with Pygments macros.

    The LaTeX writer renders a parsed literal as plain ``sphinxalltt``, which has no
    frame, caption, or highlighting. Sphinx defines the ``\PYG`` macros used here for
    its own code blocks.
    """
    body = "".join(_latex_tokens(self, node))
    self.body.append(
        f"\n\\begin{{sphinxVerbatim}}[commandchars=\\\\\\{{\\}}]\n{body}\n\\end{{sphinxVerbatim}}\n"
    )
    raise nodes.SkipNode


def _latex_tokens(self: LaTeXTranslator, node: nodes.Element) -> Iterator[str]:
    for child in node.children:
        if isinstance(child, nodes.reference):
            refid = f"{self.curfilestack[-1]}:{child['refid']}"
            label = "".join(self.hypertarget(i) for i in child["ids"])
            inner = "".join(_latex_tokens(self, child))
            yield f"{label}{self.hyperlink(refid)}\\sphinxsamedocref{{{inner}}}}}}}"
        elif isinstance(child, nodes.inline):
            yield _latex_token(child.astext(), child["classes"])


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
        f"\\PYG{{{style}}}{{{line}}}" if line else "" for line in text.split("\n")
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
