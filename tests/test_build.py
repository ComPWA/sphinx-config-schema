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


def describe_config_schema_directive():
    def it_turns_keys_into_anchors(html_dir: Path):
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

    def it_adds_tooltips(html_dir: Path):
        (tips_file,) = (html_dir / "_static" / "tippy").glob("index.*.js")
        tips = tips_file.read_text()
        assert R'"a[href=\"#tool.example.output-toml\"]"' in tips
        assert "Output <code>directory</code>." in tips
        assert "Server settings." in tips
        assert "Example settings." in tips
        assert "Examples: <code>80</code>" in tips
        assert (html_dir / "_static" / "config-schema.css").is_file()

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
        ids=["yaml", "json"],
    )
    def it_renders_other_formats(tmp_path: Path, fmt: str, expected: str):
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

    def it_warns_about_missing_values_in_strict_mode(tmp_path: Path):
        app = _build(
            tmp_path,
            dedent("""
                .. config-schema:: example.schema.json
                   :strict:
            """),
        )
        assert (
            "Settings without a default or example: missing" in app.warning.getvalue()
        )

    @pytest.mark.parametrize(
        "schema", [None, {"properties": {"output": {"default": "build"}}}]
    )
    def it_suffixes_duplicate_anchors(tmp_path: Path, schema):
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
        ids = [
            a["id"] for a in soup.select("a.config-schema-key") if "output" in a["id"]
        ]
        assert ids == ["output-yaml", "output-yaml-2", "output-json"]

    @pytest.mark.parametrize("keyword", ["anyOf", "oneOf"])
    def it_describes_nullable_enums_in_tooltips(tmp_path: Path, keyword: str):
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

    def describe_name_option():
        @pytest.mark.parametrize("fmt", ["toml", "yaml", "json"])
        def it_creates_reference_targets(tmp_path: Path, fmt: str):
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
            soup = BeautifulSoup(
                (app.outdir / "references.html").read_text(), "html.parser"
            )
            links = {
                a.get_text(): a["href"] for a in soup.select("a.reference.internal")
            }
            assert links["Example"] == "index.html#settings"
            assert links["Output"] == "index.html#settings.tool.example.output"
            assert links["Server"] == "index.html#settings.tool.example.server"

        def it_warns_about_duplicate_names(tmp_path: Path):
            app = _build(
                tmp_path,
                ".. config-schema:: example.schema.json\n   :name: settings\n\n" * 2,
            )
            assert (
                'Duplicate explicit target name: "settings"' in app.warning.getvalue()
            )

    def describe_other_builders():
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
        def it_writes_examples(
            tmp_path: Path, builder: str, output: str, expected: str
        ):
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

        def it_renders_latex_code_blocks(tmp_path: Path):
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


def describe_references():
    def it_resolves_ref_targets(tmp_path: Path):
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

    def it_resolves_option_role(tmp_path: Path):
        app = _build(
            tmp_path,
            directive=dedent("""
                :config-schema:option:`index:tool.example.output-toml`
                :config-schema:option:`Server <index:tool.example.server-toml>`
                :config-schema:option:`index:tool.example.missing`
                :config-schema:option:`index:tool.example.server.port-json`

                .. config-schema:: example.schema.json
                   :table: tool.example

                .. config-schema:: example.schema.json
                   :table: tool.example
                   :format: json
            """),
        )
        assert "tool.example.missing" in app.warning.getvalue()
        soup = BeautifulSoup((app.outdir / "index.html").read_text(), "html.parser")
        links = {a.get_text(): a["href"] for a in soup.select("p a.reference.internal")}
        assert links == {
            "output": "#tool.example.output-toml",
            "Server": "#tool.example.server-toml",
            "server.port": "#tool.example.server.port-json",
        }
        assert soup.select_one('p a[href="#tool.example.output-toml"] code')
        assert soup.select_one('p a[href="#tool.example.server-toml"] code')

    def it_option_role_shorthands(tmp_path: Path):
        app = _build(
            tmp_path,
            directive=dedent("""
                :cfg:`.output`
                :cfg:`.example.server.port`
                :cfg:`~.port`
                :config-schema:option:`~settings.tool.example.server.port`
                :cfg:`.missing`

                .. config-schema:: example.schema.json
                   :name: settings
                   :table: tool.example
            """),
        )
        warnings = app.warning.getvalue()
        assert ".missing" in warnings
        assert "more than one" not in warnings
        soup = BeautifulSoup((app.outdir / "index.html").read_text(), "html.parser")
        links = [
            (a.get_text(), a["href"]) for a in soup.select("p a.reference.internal")
        ]
        assert links == [
            ("output", "#settings.tool.example.output"),
            ("server.port", "#settings.tool.example.server.port"),
            ("port", "#settings.tool.example.server.port"),
            ("port", "#settings.tool.example.server.port"),
        ]
        assert all(soup.select('p a[href^="#settings"] code'))

    def it_option_suffix_prefers_current_document(tmp_path: Path):
        app = _build(
            tmp_path,
            directive=dedent("""
                :cfg:`.output`

                .. config-schema:: example.schema.json
                   :table: tool.example

                .. config-schema:: example.schema.json
                   :table: tool.example
                   :format: json

                .. toctree::

                   other
            """),
            documents={
                "other.rst": dedent("""
                    Other
                    =====

                    :cfg:`.server.port`

                    .. config-schema:: example.schema.json
                       :name: other
                       :table: tool.example
                """),
            },
        )
        warnings = app.warning.getvalue()
        assert "more than one option found for '.output'" in warnings
        assert "'.server.port'" not in warnings
        other = BeautifulSoup((app.outdir / "other.html").read_text(), "html.parser")
        link = other.select_one("p a.reference.internal")
        assert link is not None
        assert link["href"] == "#other.tool.example.server.port"

    def it_option_role_alias(tmp_path: Path):
        app = _build(
            tmp_path,
            directive=dedent("""
                :cfg:`settings.tool.example.output`
                :cfg:`Port <settings.tool.example.server.port>`
                :cfg:`settings.tool.example.missing`

                .. config-schema:: example.schema.json
                   :name: settings
                   :table: tool.example
            """),
        )
        assert (
            "config-schema:option reference target not found" in app.warning.getvalue()
        )
        soup = BeautifulSoup((app.outdir / "index.html").read_text(), "html.parser")
        links = {a.get_text(): a["href"] for a in soup.select("p a.reference.internal")}
        assert links == {
            "output": "#settings.tool.example.output",
            "Port": "#settings.tool.example.server.port",
        }
        assert soup.select_one('p a[href="#settings.tool.example.output"] code')

    def it_option_role_fallback_title(tmp_path: Path):
        app = _build(
            tmp_path,
            directive=dedent("""
                :cfg:`!.output` :cfg:`!~.server.port` :cfg:`.nope`

                .. config-schema:: example.schema.json
                   :table: tool.example
            """),
        )
        assert "target not found: .nope" in app.warning.getvalue()
        soup = BeautifulSoup((app.outdir / "index.html").read_text(), "html.parser")
        paragraph = soup.select_one("p")
        assert paragraph is not None
        assert not paragraph.select("a")
        assert [c.get_text() for c in paragraph.select("code")] == [
            "output",
            "port",
            "nope",
        ]
