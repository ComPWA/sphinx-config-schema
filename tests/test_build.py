from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from bs4 import BeautifulSoup
from sphinx.testing.util import SphinxTestApp

if TYPE_CHECKING:
    from pathlib import Path

SCHEMA = {
    "properties": {
        "output": {"description": "Output ``directory``.", "default": "build"},
        "missing": {"description": "No value."},
        "server": {
            "type": "object",
            "properties": {"port": {"description": "Port.", "default": 8080}},
        },
    }
}


def _build(tmp_path: Path, directive: str, builder: str = "html") -> SphinxTestApp:
    src = tmp_path / "src"
    src.mkdir()
    (src / "conf.py").write_text('extensions = ["sphinx_toml_schema"]\n')
    (src / "example.schema.json").write_text(json.dumps(SCHEMA))
    (src / "index.rst").write_text(f"Example\n=======\n\n{directive}")
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
        ".. toml-schema:: example.schema.json\n"
        "   :caption: pyproject.toml\n"
        "   :table: tool.example\n",
    )
    assert not app.warning.getvalue()
    return app.outdir


def test_strict(tmp_path: Path):
    app = _build(tmp_path, ".. toml-schema:: example.schema.json\n   :strict:\n")
    assert "Settings without a default or example: missing" in app.warning.getvalue()


@pytest.mark.parametrize(
    ("fmt", "expected"),
    [
        ("yaml", "tool:\n  example:\n    output: build\n    server:\n      port: 8080"),
        (
            "json",
            (
                '{\n  "tool": {\n    "example": {\n      "output": "build",\n'
                '      "server": {\n        "port": 8080\n      }\n    }\n  }\n}'
            ),
        ),
    ],
)
def test_formats(tmp_path: Path, fmt: str, expected: str):
    app = _build(
        tmp_path,
        ".. toml-schema:: example.schema.json\n"
        "   :table: tool.example\n"
        f"   :format: {fmt}\n",
    )
    assert not app.warning.getvalue()
    soup = BeautifulSoup((app.outdir / "index.html").read_text(), "html.parser")
    code = soup.select_one(f".highlight-{fmt} pre")
    assert code is not None
    assert code.get_text() == expected
    keys = {a["id"]: a.get_text() for a in soup.select("a.toml-schema-key")}
    assert set(keys) == {"tool-example-output", "tool-example-server-port"}


def test_keys_are_anchors(html_dir: Path):
    soup = BeautifulSoup((html_dir / "index.html").read_text(), "html.parser")
    keys = {a["id"]: a.get_text() for a in soup.select("a.toml-schema-key")}
    assert keys == {
        "tool-example-output": "output",
        "tool-example-server-port": "port",
    }
    code = soup.select_one(".highlight-toml pre")
    assert code is not None
    assert code.get_text() == (
        '[tool.example]\noutput = "build"\n\n[tool.example.server]\nport = 8080'
    )


def test_tooltips(html_dir: Path):
    (tips_file,) = (html_dir / "_static" / "tippy").glob("index.*.js")
    tips = tips_file.read_text()
    assert '"a[href=\\"#tool-example-output\\"]"' in tips
    assert "Output <code>directory</code>." in tips
    assert (html_dir / "_static" / "toml-schema.css").is_file()


@pytest.mark.parametrize(
    ("builder", "output", "expected"),
    [
        ("text", "index.txt", "[tool.example.server]"),
        (
            "latex",
            "projectnamenotset.tex",  # cspell:ignore projectnamenotset
            r"\label{\detokenize{index:tool-example-server-port}}",
        ),
    ],
)
def test_other_builders(tmp_path: Path, builder: str, output: str, expected: str):
    app = _build(
        tmp_path,
        ".. toml-schema:: example.schema.json\n   :table: tool.example\n",
        builder=builder,
    )
    assert not app.warning.getvalue()
    assert expected in (app.outdir / output).read_text()


def test_duplicate_anchors_get_suffix(tmp_path: Path):
    directive = ".. toml-schema:: example.schema.json\n   :format: {}\n\n"
    app = _build(
        tmp_path, "".join(directive.format(f) for f in ("yaml", "yaml", "json"))
    )
    assert not app.warning.getvalue()
    soup = BeautifulSoup((app.outdir / "index.html").read_text(), "html.parser")
    ids = [a["id"] for a in soup.select("a.toml-schema-key") if "output" in a["id"]]
    assert ids == ["output", "output-yaml", "output-json"]
