import pytest
from docutils import nodes

from sphinx_config_schema.codeblock import create_literal_block
from sphinx_config_schema.render import render
from sphinx_config_schema.schema import Setting


def describe_create_literal_block():
    @pytest.mark.parametrize(
        ("fmt", "key"),
        [
            ("toml", '"web.example.edu"'),
            ("yaml", "web.example.edu"),
            ("json", '"web.example.edu"'),
        ],
    )
    def it_turns_keys_into_anchors(fmt: str, key: str):
        settings = [Setting(("tool", "demo"), "web.example.edu", "x", "")]
        block = create_literal_block(settings, fmt, rawsource="config-schema")
        (reference,) = block.findall(nodes.reference)
        assert reference["ids"] == ["tool.demo.web-example-edu"]
        assert reference.astext() == key  # cspell:ignore astext
        assert block.astext() == render(settings, fmt)

    def it_anchors_commented_out_keys():
        settings = [Setting((), "mode", "a", "", default=None)]
        block = create_literal_block(settings, "toml", rawsource="config-schema")
        (reference,) = block.findall(nodes.reference)
        assert reference["ids"] == ["mode"]
        assert reference.astext() == "mode"
        assert block.astext() == '# mode = "a"'
