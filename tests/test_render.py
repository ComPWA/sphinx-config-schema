import tomllib

import pytest
from docutils import nodes

from sphinx_toml_schema import Setting, create_literal_block, iter_settings, render_toml


def test_rendered_toml_is_valid():
    schema = {
        "properties": {
            "flag": {"default": True},
            "ratio": {"default": 0.5},
            "paths": {"default": ["a", "b"]},
            "options": {"default": {"key with space": 1}},
            "web.example.edu": {"examples": ["quoted key"]},
            "missing": {"description": "No value, so it is skipped."},
            "nested": {
                "type": "object",
                "properties": {"depth": {"default": 2}},
            },
        }
    }
    source = render_toml(list(iter_settings(schema, table="tool.demo")))
    assert tomllib.loads(source) == {
        "tool": {
            "demo": {
                "flag": True,
                "ratio": 0.5,
                "paths": ["a", "b"],
                "options": {"key with space": 1},
                "web.example.edu": "quoted key",
                "nested": {"depth": 2},
            }
        }
    }


def test_without_table():
    schema = {"properties": {"name": {"default": "demo"}}}
    source = render_toml(list(iter_settings(schema)))
    assert source == 'name = "demo"'


def test_quoted_keys_become_anchors():
    settings = [Setting("tool.demo", "web.example.edu", "x", "")]
    block = create_literal_block(settings, rawsource="toml-schema")
    (reference,) = block.findall(nodes.reference)
    assert reference["ids"] == ["tool-demo-web-example-edu"]
    assert reference.astext() == '"web.example.edu"'  # cspell:ignore astext


def test_unsupported_value():
    with pytest.raises(TypeError, match="Cannot render"):
        render_toml([Setting("", "value", object(), "")])
