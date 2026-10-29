import json
import tomllib

import pytest
import yaml
from docutils import nodes

from sphinx_toml_schema import Setting, create_literal_block, iter_settings, render

SCHEMA = {
    "properties": {
        "flag": {"default": True},
        "ratio": {"default": 0.5},
        "paths": {"default": ["a", "b"]},
        "options": {"default": {"key with space": 1, "no": "yes"}},
        "web.example.edu": {"examples": ["quoted key"]},
        "version": {"default": "1.0"},
        "missing": {"description": "No value, so it is skipped."},
        "nested": {
            "type": "object",
            "properties": {"depth": {"default": 2}},
        },
        "empty": {"type": "object", "properties": {"missing": {}}},
    }
}
EXPECTED = {
    "tool": {
        "demo": {
            "flag": True,
            "ratio": 0.5,
            "paths": ["a", "b"],
            "options": {"key with space": 1, "no": "yes"},
            "web.example.edu": "quoted key",
            "version": "1.0",
            "nested": {"depth": 2},
        }
    }
}


@pytest.mark.parametrize(
    ("fmt", "load"),
    [("toml", tomllib.loads), ("yaml", yaml.safe_load), ("json", json.loads)],
)
def test_rendered_example_is_valid(fmt: str, load):
    source = render(list(iter_settings(SCHEMA, table=("tool", "demo"))), fmt)
    assert load(source) == EXPECTED
    assert not source.endswith("\n")


@pytest.mark.parametrize(
    ("fmt", "expected"),
    [
        ("toml", 'name = "demo"'),
        ("yaml", "name: demo"),
        ("json", '{\n  "name": "demo"\n}'),
    ],
)
def test_without_table(fmt: str, expected: str):
    schema = {"properties": {"name": {"default": "demo"}}}
    assert render(list(iter_settings(schema)), fmt) == expected


def test_empty_json():
    assert render([], "json") == "{}"


@pytest.mark.parametrize(
    ("fmt", "key"),
    [
        ("toml", '"web.example.edu"'),
        ("yaml", "web.example.edu"),
        ("json", '"web.example.edu"'),
    ],
)
def test_keys_become_anchors(fmt: str, key: str):
    settings = [Setting(("tool", "demo"), "web.example.edu", "x", "")]
    block = create_literal_block(settings, fmt, rawsource="toml-schema")
    (reference,) = block.findall(nodes.reference)
    assert reference["ids"] == ["tool-demo-web-example-edu"]
    assert reference.astext() == key  # cspell:ignore astext
    assert block.astext() == render(settings, fmt)


@pytest.mark.parametrize("fmt", ["toml", "yaml", "json"])
def test_unsupported_value(fmt: str):
    with pytest.raises(TypeError, match="Cannot render"):
        render([Setting((), "value", object(), "")], fmt)


def test_unknown_format():
    with pytest.raises(ValueError, match="Unknown format"):
        render([], "ini")
