import pytest

from sphinx_config_schema.tooltips import to_tooltip


def describe_to_tooltip():
    def it_wraps_text_in_a_paragraph():
        assert to_tooltip("Plain text.") == "<p>Plain text.</p>"

    def it_turns_inline_literals_into_code():
        assert (
            to_tooltip("Use ``-n auto`` or ``--no-cov``.")
            == "<p>Use <code>-n auto</code> or <code>--no-cov</code>.</p>"
        )

    @pytest.mark.parametrize(
        ("description", "expected"),
        [
            ("a < b & c", "<p>a &lt; b &amp; c</p>"),
            ("``<tag>``", "<p><code>&lt;tag&gt;</code></p>"),
        ],
    )
    def it_escapes_html(description: str, expected: str):
        assert to_tooltip(description) == expected

    def it_leaves_unpaired_backticks():
        assert to_tooltip("A ``b") == "<p>A ``b</p>"
