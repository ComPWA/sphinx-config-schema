from __future__ import annotations

import json
from textwrap import dedent
from typing import TYPE_CHECKING, Any

import pytest
from bs4 import BeautifulSoup
from sphinx.testing.util import SphinxTestApp

if TYPE_CHECKING:
    from pathlib import Path

SCHEMA = {
    "description": "Example settings.",
    "properties": {
        "output": {"description": "Output ``directory``.", "default": "build"},
        "missing": {"description": "No value."},
        "server": {
            "type": "object",
            "description": "Server settings.",
            "properties": {
                "port": {"description": "Port.", "default": 8080, "examples": [80]}
            },
        },
    },
}


def _build(
    tmp_path: Path,
    directive: str,
    builder: str = "html",
    *,
    schema: dict[str, Any] | None = None,
    documents: dict[str, str] | None = None,
) -> SphinxTestApp:
    src = tmp_path / "src"
    src.mkdir()
    (src / "conf.py").write_text('extensions = ["sphinx_config_schema"]\n')
    (src / "example.schema.json").write_text(
        json.dumps(SCHEMA if schema is None else schema)
    )
    (src / "index.rst").write_text(f"Example\n=======\n\n{directive}")
    for name, content in (documents or {}).items():
        (src / name).write_text(content)
    app = SphinxTestApp(builder, srcdir=src, builddir=tmp_path / "build")
    try:
        app.build()
    finally:
        app.cleanup()
    return app


@pytest.fixture(scope="module")
def html_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    app = _build(
        tmp_path_factory.mktemp("build"),
        dedent("""
            .. config-schema:: example.schema.json
               :caption: pyproject.toml
               :table: tool.example
        """),
    )
    assert not app.warning.getvalue()
    return app.outdir


def test_strict(tmp_path: Path):
    app = _build(
        tmp_path,
        dedent("""
            .. config-schema:: example.schema.json
               :strict:
        """),
    )
    assert "Settings without a default or example: missing" in app.warning.getvalue()


@pytest.mark.parametrize(
    ("fmt", "expected"),
    [
        (
            "yaml",
            dedent("""\
                tool:
                  example:
                    output: build
                    server:
                      port: 8080"""),
        ),
        (
            "json",
            dedent("""\
                {
                  "tool": {
                    "example": {
                      "output": "build",
                      "server": {
                        "port": 8080
                      }
                    }
                  }
                }"""),
        ),
    ],
)
def test_formats(tmp_path: Path, fmt: str, expected: str):
    app = _build(
        tmp_path,
        dedent(f"""
            .. config-schema:: example.schema.json
               :table: tool.example
               :format: {fmt}
        """),
    )
    assert not app.warning.getvalue()
    soup = BeautifulSoup((app.outdir / "index.html").read_text(), "html.parser")
    code = soup.select_one(f".highlight-{fmt} pre")
    assert code is not None
    assert code.get_text() == expected
    keys = {a["id"]: a.get_text() for a in soup.select("a.config-schema-key")}
    assert set(keys) == {
        f"tool.example-{fmt}",
        f"tool.example.output-{fmt}",
        f"tool.example.server-{fmt}",
        f"tool.example.server.port-{fmt}",
    }


def test_keys_are_anchors(html_dir: Path):
    soup = BeautifulSoup((html_dir / "index.html").read_text(), "html.parser")
    keys = {a["id"]: a.get_text() for a in soup.select("a.config-schema-key")}
    assert keys == {
        "tool.example-toml": "example",
        "tool.example.output-toml": "output",
        "tool.example.server-toml": "server",
        "tool.example.server.port-toml": "port",
    }
    code = soup.select_one(".highlight-toml pre")
    assert code is not None
    assert code.get_text() == dedent("""\
        [tool.example]
        output = "build"

        [tool.example.server]
        port = 8080""")


def test_option_references(tmp_path: Path):
    app = _build(
        tmp_path,
        dedent("""
            :ref:`Output <index:tool.example.output-toml>`
            :ref:`Server <index:tool.example.server-toml>`
            :ref:`JSON output <index:tool.example.output-json>`

            .. config-schema:: example.schema.json
               :table: tool.example

            .. config-schema:: example.schema.json
               :table: tool.example
               :format: json
        """),
    )
    assert not app.warning.getvalue()
    soup = BeautifulSoup((app.outdir / "index.html").read_text(), "html.parser")
    links = {a.get_text(): a["href"] for a in soup.select("a.reference.internal")}
    assert links["Output"] == "#tool.example.output-toml"
    assert links["Server"] == "#tool.example.server-toml"
    assert links["JSON output"] == "#tool.example.output-json"


@pytest.mark.parametrize("fmt", ["toml", "yaml", "json"])
def test_named_example(tmp_path: Path, fmt: str):
    app = _build(
        tmp_path,
        dedent(f"""
            .. config-schema:: example.schema.json
               :name: settings
               :format: {fmt}
               :table: tool.example

            .. toctree::

               references
        """),
        documents={
            "references.rst": dedent("""
                References
                ==========

                :ref:`Example <settings>`
                :ref:`Output <settings.tool.example.output>`
                :ref:`Server <settings.tool.example.server>`
            """),
        },
    )
    assert not app.warning.getvalue()
    soup = BeautifulSoup((app.outdir / "references.html").read_text(), "html.parser")
    links = {a.get_text(): a["href"] for a in soup.select("a.reference.internal")}
    assert links["Example"] == "index.html#settings"
    assert links["Output"] == "index.html#settings.tool.example.output"
    assert links["Server"] == "index.html#settings.tool.example.server"


def test_duplicate_example_name(tmp_path: Path):
    app = _build(
        tmp_path,
        ".. config-schema:: example.schema.json\n   :name: settings\n\n" * 2,
    )
    assert 'Duplicate explicit target name: "settings"' in app.warning.getvalue()


def test_tooltips(html_dir: Path):
    (tips_file,) = (html_dir / "_static" / "tippy").glob("index.*.js")
    tips = tips_file.read_text()
    assert '"a[href=\\"#tool.example.output-toml\\"]"' in tips
    assert "Output <code>directory</code>." in tips
    assert "Server settings." in tips
    assert "Example settings." in tips
    assert "Examples: <code>80</code>" in tips
    assert (html_dir / "_static" / "config-schema.css").is_file()


@pytest.mark.parametrize(
    ("builder", "output", "expected"),
    [
        ("text", "index.txt", "[tool.example.server]"),
        (
            "latex",
            "projectnamenotset.tex",  # cspell:ignore projectnamenotset
            r"\label{\detokenize{index:tool.example.server.port-toml}}",
        ),
    ],
)
def test_other_builders(tmp_path: Path, builder: str, output: str, expected: str):
    app = _build(
        tmp_path,
        dedent("""
            .. config-schema:: example.schema.json
               :table: tool.example
        """),
        builder=builder,
    )
    assert not app.warning.getvalue()
    assert expected in (app.outdir / output).read_text()


def test_latex_code_block(tmp_path: Path):
    app = _build(
        tmp_path,
        dedent("""
            .. config-schema:: example.schema.json
               :caption: pyproject.toml
               :table: tool.example
        """),
        builder="latex",
    )
    assert not app.warning.getvalue()
    # cspell:ignore commandchars hyperref phantomsection sphinxalltt sphinxsamedocref
    tex = (app.outdir / "projectnamenotset.tex").read_text()
    assert r"\sphinxSetupCaptionForVerbatim{pyproject.toml}" in tex
    assert r"\begin{sphinxVerbatim}[commandchars=\\\{\}]" in tex
    assert "sphinxalltt" not in tex
    assert (
        r"\phantomsection\label{\detokenize{index:tool.example.server.port-toml}}"
        r"{\hyperref[\detokenize{index:tool.example.server.port-toml}]"
        r"{\sphinxsamedocref{\PYG{n}{port}}}}"
    ) in tex


@pytest.mark.parametrize(
    "schema", [None, {"properties": {"output": {"default": "build"}}}]
)
def test_duplicate_anchors_get_suffix(tmp_path: Path, schema):
    directive = dedent("""
        .. config-schema:: example.schema.json
           :format: {}
    """)
    app = _build(
        tmp_path,
        directive="".join(directive.format(f) for f in ("yaml", "yaml", "json")),
        schema=schema,
    )
    assert not app.warning.getvalue()
    soup = BeautifulSoup((app.outdir / "index.html").read_text(), "html.parser")
    ids = [a["id"] for a in soup.select("a.config-schema-key") if "output" in a["id"]]
    assert ids == ["output-yaml", "output-yaml-2", "output-json"]


@pytest.mark.parametrize("keyword", ["anyOf", "oneOf"])
def test_nullable_enum_tooltip(tmp_path: Path, keyword: str):
    schema = {
        "$defs": {"Mode": {"enum": ["a", "b"]}},
        "properties": {
            "mode": {
                keyword: [{"$ref": "#/$defs/Mode"}, {"type": "null"}],
                "default": None,
                "description": "Choose a mode.",
            }
        },
    }
    app = _build(
        tmp_path,
        dedent("""
            .. config-schema:: example.schema.json
               :strict:
        """),
        schema=schema,
    )
    assert not app.warning.getvalue()
    soup = BeautifulSoup((app.outdir / "index.html").read_text(), "html.parser")
    code = soup.select_one(".highlight-toml pre")
    assert code is not None
    assert code.get_text() == '# mode = "a"'
    (tips_file,) = (app.outdir / "_static" / "tippy").glob("index.*.js")
    tips = tips_file.read_text()
    assert "Choose a mode." in tips
    assert "Default: <code>null</code>" in tips
    assert "Example (inferred from enum):" in tips
    assert "Allowed values:" in tips
    assert "&quot;a&quot;" in tips
    assert "&quot;b&quot;" in tips
