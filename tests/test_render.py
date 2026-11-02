import json
import tomllib

import pytest
import yaml

from sphinx_config_schema.render import render
from sphinx_config_schema.schema import Setting, iter_settings

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


def describe_render():
    @pytest.mark.parametrize(
        ("fmt", "load"),
        [("toml", tomllib.loads), ("yaml", yaml.safe_load), ("json", json.loads)],
    )
    def it_produces_valid_source(fmt: str, load):
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
    def it_renders_without_table(fmt: str, expected: str):
        schema = {"properties": {"name": {"default": "demo"}}}
        assert render(list(iter_settings(schema)), fmt) == expected

    def it_renders_empty_json():
        assert render([], "json") == "{}"

    @pytest.mark.parametrize("fmt", ["toml", "yaml", "json"])
    def it_rejects_unsupported_values(fmt: str):
        with pytest.raises(TypeError, match="Cannot render"):
            render([Setting((), "value", object(), "")], fmt)

    def it_rejects_unknown_formats():
        with pytest.raises(ValueError, match="Unknown format"):
            render([], "ini")

    @pytest.mark.parametrize(
        ("fmt", "load", "expected"),
        [
            ("toml", tomllib.loads, {}),
            ("yaml", yaml.safe_load, {"mode": None}),
            ("json", json.loads, {"mode": None}),
        ],
    )
    def it_shows_null_defaults_as_null(fmt: str, load, expected: dict):
        settings = [Setting((), "mode", "a", "", default=None)]
        assert load(render(settings, fmt)) == expected

    def it_comments_out_null_defaults_in_toml():
        settings = [Setting((), "mode", "a", "", default=None)]
        assert render(settings, "toml") == '# mode = "a"'

    @pytest.mark.parametrize(
        ("fmt", "expected"),
        [("toml", 'mode = "b"'), ("yaml", "mode: b"), ("json", '{\n  "mode": "b"\n}')],
    )
    def it_keeps_non_null_defaults_active(fmt: str, expected: str):
        settings = [Setting((), "mode", "b", "", default="b")]
        assert render(settings, fmt) == expected
