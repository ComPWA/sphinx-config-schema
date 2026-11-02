"""Render a JSON schema as a copyable TOML, YAML, or JSON example in Sphinx."""

# cspell:ignore contnode docname docnames fromdocname innernodeclass otherdata refexplicit refnode relfn

from __future__ import annotations

import importlib.metadata
import itertools
import json
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, cast

from docutils import nodes
from docutils.parsers.rst import directives
from sphinx.directives.code import container_wrapper
from sphinx.domains import Domain
from sphinx.roles import XRefRole
from sphinx.util.docutils import SphinxDirective
from sphinx.util.nodes import make_refnode
from typing_extensions import override

from sphinx_config_schema.codeblock import (
    _example_block,
    _visit_example_block_latex,
    create_literal_block,
)
from sphinx_config_schema.render import FORMATS
from sphinx_config_schema.schema import Entry, Setting, iter_settings
from sphinx_config_schema.tooltips import (
    _entry_tooltip,
    _get_tips,
    _merge_tips,
    _purge_tips,
    _register_tips,
)

if TYPE_CHECKING:
    from collections.abc import Set as AbstractSet

    from sphinx.addnodes import pending_xref
    from sphinx.application import Sphinx
    from sphinx.builders import Builder
    from sphinx.environment import BuildEnvironment


class ConfigSchemaDirective(SphinxDirective):
    """Render a copyable TOML, YAML, or JSON example from a JSON schema.

    Each key in the example is an anchor that sphinx-tippy turns into a tooltip with the
    description of that setting and the values that the example does not show.
    """

    has_content = False
    required_arguments = 1
    option_spec = MappingProxyType({
        "caption": directives.unchanged_required,
        "format": lambda arg: directives.choice(arg, FORMATS),
        "name": directives.unchanged_required,
        "strict": directives.flag,
        "table": directives.unchanged_required,
    })

    @override
    def run(self) -> list[nodes.Node]:
        rel_path, abs_path = self.env.relfn2path(self.arguments[0])
        self.env.note_dependency(rel_path)
        schema = json.loads(Path(abs_path).read_text())
        table = (
            tuple(self.options.get("table", "").split("."))
            if "table" in self.options
            else ()
        )
        fmt = self.options.get("format", "toml")
        strict = "strict" in self.options
        try:
            settings = list(iter_settings(schema, table=table, strict=strict))
        except ValueError as exc:
            raise self.error(str(exc)) from exc
        tips: dict[str, str] = _get_tips(self.env).setdefault(self.env.docname, {})
        name = self.options.get("name")
        used = set(self.state.document.ids)
        settings = [
            _make_unique(
                replace(s, _anchor_prefix=name or ""),
                "" if name else fmt,
                used,
            )
            for s in _drop_empty_tables(settings)
        ]
        tips.update({
            f"#{s.anchor}": tip for s in settings if (tip := _entry_tooltip(s))
        })
        example = create_literal_block(settings, fmt, rawsource=self.name)
        self._register_labels(example, settings, name)
        self.set_source_info(example)
        caption = self.options.get("caption")
        if caption is not None:
            example = container_wrapper(self, example, caption)
        self.add_name(example)
        return [example]

    def _register_labels(
        self, example: nodes.Element, settings: list[Entry], name: str | None
    ) -> None:
        """Make each key a target for :rst:role:`ref` and the option role."""
        domain = cast("_ConfigSchemaDomain", self.env.get_domain("config-schema"))
        keys = {s.anchor: s.name for s in settings}
        for key in example.findall(nodes.reference):
            anchor = key["ids"][0]
            label = anchor if name else f"{self.env.docname}:{anchor}"
            key["names"].append(label)
            self.state.document.note_explicit_target(key)
            domain.options[label] = (self.env.docname, anchor, keys[anchor])


def _drop_empty_tables(entries: list[Entry]) -> list[Entry]:
    """Remove the tables that do not appear in the example, as no setting is in them."""
    used = {
        s.table[:i]
        for s in entries
        if isinstance(s, Setting)
        for i in range(len(s.table) + 1)
    }
    return [e for e in entries if isinstance(e, Setting) or e.path in used]


def _make_unique(setting: Entry, fmt: str, used: set[str]) -> Entry:
    """Reserve a unique anchor, including the format for unnamed examples.

    This happens when the same schema is shown in several formats, for instance in tabs.

    >>> used = {"port-yaml"}
    >>> _make_unique(Setting((), "port", 80, ""), "yaml", used).anchor
    'port-yaml-2'
    """
    base = f"-{fmt}" if fmt else ""
    suffixes = itertools.chain((base,), (f"{base}-{i}" for i in itertools.count(2)))
    candidates = (replace(setting, _anchor_suffix=s) for s in suffixes)
    result = next(c for c in candidates if c.anchor not in used)
    used.add(result.anchor)
    return result


class _ConfigSchemaDomain(Domain):
    """Resolve references to the keys of a :rst:dir:`config-schema` example.

    The :rst:role:`config-schema:option` role takes the same labels as :rst:role:`ref`,
    but renders the link as inline code and titles it with the key by default.
    """

    name = "config-schema"
    label = "Configuration schema"
    roles = {"option": XRefRole(innernodeclass=nodes.literal, warn_dangling=True)}  # ruff: ignore[mutable-class-default]
    initial_data = {"options": {}}  # ruff: ignore[mutable-class-default]

    @property
    def options(self) -> dict[str, tuple[str, str, str]]:
        """Document, anchor, and key text per label."""
        return self.data["options"]

    @override
    def clear_doc(self, docname: str) -> None:
        for label, (doc, *_) in list(self.options.items()):
            if doc == docname:
                del self.options[label]

    @override
    def merge_domaindata(
        self, docnames: AbstractSet[str], otherdata: dict[str, Any]
    ) -> None:
        self.options.update({
            label: entry
            for label, entry in otherdata["options"].items()
            if entry[0] in docnames
        })

    @override
    def resolve_xref(
        self,
        env: BuildEnvironment,
        fromdocname: str,
        builder: Builder,
        typ: str,
        target: str,
        node: pending_xref,
        contnode: nodes.Element,
    ) -> nodes.reference | None:
        if target not in self.options:
            return None
        docname, anchor, key = self.options[target]
        if not node.get("refexplicit"):
            contnode = nodes.literal(key, key)
        return make_refnode(builder, fromdocname, docname, anchor, contnode, key)

    @override
    def resolve_any_xref(
        self,
        env: BuildEnvironment,
        fromdocname: str,
        builder: Builder,
        target: str,
        node: pending_xref,
        contnode: nodes.Element,
    ) -> list[tuple[str, nodes.reference]]:
        return []


def setup(app: Sphinx) -> dict[str, Any]:
    app.setup_extension("sphinx_tippy")
    app.add_domain(_ConfigSchemaDomain)
    app.add_directive("config-schema", ConfigSchemaDirective)
    app.add_node(_example_block, latex=(_visit_example_block_latex, None))
    app.connect("builder-inited", _add_static_path)
    app.connect("env-purge-doc", _purge_tips)
    app.connect("env-merge-info", _merge_tips)
    app.connect("html-page-context", _register_tips, priority=400)
    return {
        "parallel_read_safe": True,
        "parallel_write_safe": True,
        "version": importlib.metadata.version("sphinx-config-schema"),
    }


def _add_static_path(app: Sphinx) -> None:
    app.config.html_static_path.append(str(Path(__file__).parent / "_static"))
    app.add_css_file("config-schema.css")
