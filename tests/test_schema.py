import json
import tomllib

import pytest
import yaml
from docutils import nodes

from sphinx_config_schema.codeblock import create_literal_block
from sphinx_config_schema.render import render
from sphinx_config_schema.schema import Setting, iter_settings


def describe_iter_settings():
    @pytest.mark.parametrize("keyword", ["anyOf", "oneOf"])
    @pytest.mark.parametrize("referenced", [False, True], ids=["inline", "reference"])
    @pytest.mark.parametrize("default", [None, "b"])
    def it_lists_nullable_enum_choices(tmp_path, keyword, referenced, default):
        enum = {"enum": ["a", "b"], "type": "string"}
        schema = {
            "$defs": {"Mode": enum},
            "properties": {
                "mode": {
                    keyword: [
                        {"type": "null"},
                        {"$ref": "#/$defs/Mode"} if referenced else enum,
                    ],
                    "default": default,
                    "description": "Choose a mode.",
                }
            },
        }
        path = tmp_path / "schema.json"
        path.write_text(json.dumps(schema))
        settings = list(iter_settings(json.loads(path.read_text()), strict=True))
        (setting,) = settings
        assert isinstance(setting, Setting)
        assert setting.value == ("a" if default is None else default)
        assert setting.allowed == (None, "a", "b")
        assert setting.description == "Choose a mode."
        for fmt, load in [
            ("toml", tomllib.loads),
            ("yaml", yaml.safe_load),
            ("json", json.loads),
        ]:
            source = render(settings, fmt)
            if default is None and fmt == "toml":
                assert source == '# mode = "a"'
                assert load(source) == {}
            else:
                assert load(source) == {"mode": default}
        assert schema["properties"]["mode"]["default"] is default

    @pytest.mark.parametrize("example", ["b", False, 0])
    def it_prefers_explicit_examples_over_enum(tmp_path, example):
        schema = {
            "properties": {
                "mode": {
                    "default": None,
                    "enum": ["a", "b", False, 0],
                    "examples": [example],
                }
            }
        }
        path = tmp_path / "schema.json"
        path.write_text(json.dumps(schema))
        (setting,) = iter_settings(json.loads(path.read_text()))
        assert isinstance(setting, Setting)
        assert setting.value == example

    def it_resolves_referenced_enum_without_default(tmp_path):
        schema = {
            "$defs": {"Mode": {"enum": [None, "a", "b"], "description": "Mode."}},
            "properties": {"mode": {"$ref": "#/$defs/Mode"}},
        }
        path = tmp_path / "schema.json"
        path.write_text(json.dumps(schema))
        (setting,) = iter_settings(json.loads(path.read_text()), strict=True)
        assert isinstance(setting, Setting)
        assert setting.value == "a"
        assert setting.description == "Mode."
        assert setting.allowed == (None, "a", "b")

    @pytest.mark.parametrize("explicit_example", [False, True])
    def it_preserves_null_default_when_an_example_is_available(
        tmp_path, explicit_example
    ):
        field = {"default": None, "enum": ["a", "b", None]}
        if explicit_example:
            field["examples"] = ["b"]
        path = tmp_path / "schema.json"
        path.write_text(json.dumps({"properties": {"mode": field}}))
        settings = list(iter_settings(json.loads(path.read_text()), strict=True))
        example = "b" if explicit_example else "a"
        assert render(settings, "toml") == f'# mode = "{example}"'
        assert tomllib.loads(render(settings, "toml")) == {}
        assert yaml.safe_load(render(settings, "yaml")) == {"mode": None}
        assert json.loads(render(settings, "json")) == {"mode": None}
        block = create_literal_block(settings, "toml", rawsource="config-schema")
        (reference,) = block.findall(nodes.reference)
        assert reference["ids"] == ["mode"]
        assert reference.astext() == "mode"  # cspell:ignore astext

    def it_keeps_non_null_defaults_active(tmp_path):
        path = tmp_path / "schema.json"
        path.write_text(
            json.dumps({"properties": {"mode": {"default": "b", "enum": ["a", "b"]}}})
        )
        settings = list(iter_settings(json.loads(path.read_text())))
        assert render(settings, "toml") == 'mode = "b"'
        assert yaml.safe_load(render(settings, "yaml")) == {"mode": "b"}
        assert json.loads(render(settings, "json")) == {"mode": "b"}
