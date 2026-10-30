import json
import tomllib

import pytest
import yaml
from docutils import nodes

from sphinx_config_schema import Setting, create_literal_block, iter_settings, render

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
    block = create_literal_block(settings, fmt, rawsource="config-schema")
    (reference,) = block.findall(nodes.reference)
    assert reference["ids"] == ["tool.demo.web-example-edu"]
    assert reference.astext() == key  # cspell:ignore astext
    assert block.astext() == render(settings, fmt)


@pytest.mark.parametrize("fmt", ["toml", "yaml", "json"])
def test_unsupported_value(fmt: str):
    with pytest.raises(TypeError, match="Cannot render"):
        render([Setting((), "value", object(), "")], fmt)


def test_unknown_format():
    with pytest.raises(ValueError, match="Unknown format"):
        render([], "ini")


@pytest.mark.parametrize("keyword", ["anyOf", "oneOf"])
@pytest.mark.parametrize("referenced", [False, True], ids=["inline", "reference"])
@pytest.mark.parametrize("default", [None, "b"])
def test_nullable_enum_choices(tmp_path, keyword, referenced, default):
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
def test_explicit_examples_take_precedence_over_enum(tmp_path, example):
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


def test_referenced_enum_without_default(tmp_path):
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
def test_null_default_is_preserved_when_an_example_is_available(
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
    assert reference.astext() == "mode"


def test_non_null_defaults_remain_active(tmp_path):
    path = tmp_path / "schema.json"
    path.write_text(
        json.dumps({"properties": {"mode": {"default": "b", "enum": ["a", "b"]}}})
    )
    settings = list(iter_settings(json.loads(path.read_text())))
    assert render(settings, "toml") == 'mode = "b"'
    assert yaml.safe_load(render(settings, "yaml")) == {"mode": "b"}
    assert json.loads(render(settings, "json")) == {"mode": "b"}
