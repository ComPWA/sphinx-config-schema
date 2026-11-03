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
from sphinx.util import logging
from sphinx.util.docutils import SphinxDirective
from sphinx.util.nodes import make_refnode
from typing_extensions import override

from sphinx_config_schema.codeblock import (
    _example_block,
    _visit_example_block_latex,
    create_literal_block,
)
from sphinx_config_schema.render import FORMATS
from sphinx_config_schema.schema import Entry, Setting, _make_anchor, iter_settings
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


_LOGGER = logging.getLogger(__name__)
OPTION_ROLE_ALIAS = "cfg"
"""Short name under which :rst:role:`config-schema:option` is also registered."""


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
        self._register_labels(example, settings, name, table_depth=len(table))
        self.set_source_info(example)
        caption = self.options.get("caption")
        if caption is not None:
            example = container_wrapper(self, example, caption)
        self.add_name(example)
        return [example]

    def _register_labels(
        self,
        example: nodes.Element,
        settings: list[Entry],
        name: str | None,
        table_depth: int,
    ) -> None:
        """Make each key a target for :rst:role:`ref` and the option role."""
        domain = cast("_ConfigSchemaDomain", self.env.get_domain("config-schema"))
        entries = {s.anchor: s for s in settings}
        for key in example.findall(nodes.reference):
            anchor = key["ids"][0]
            label = anchor if name else f"{self.env.docname}:{anchor}"
            key["names"].append(label)
            self.state.document.note_explicit_target(key)
            entry = entries[anchor]
            title = ".".join(entry.path[table_depth:] or entry.path)
            path = _make_anchor("", entry.path, "")
            domain.options[label] = (self.env.docname, anchor, title, path)


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


class _OptionRole(XRefRole):
    """Shorten the title to the last key with ``~`` and accept an alias name."""

    @override
    def run(self) -> tuple[list[nodes.Node], list[nodes.system_message]]:
        self.name = "config-schema:option"
        return super().run()

    @override
    def process_link(
        self,
        env: BuildEnvironment,
        refnode: nodes.Element,
        has_explicit_title: bool,
        title: str,
        target: str,
    ) -> tuple[str, str]:
        if target.startswith("~"):
            refnode["config-schema:short"] = True
        if not has_explicit_title:
            title = _fallback_title(target)
        return title, target.removeprefix("~")

    @override
    def create_non_xref_node(
        self,
    ) -> tuple[list[nodes.Node], list[nodes.system_message]]:
        if not self.has_explicit_title:
            self.text = "!" + _fallback_title(self.text[1:])
        return super().create_non_xref_node()


def _fallback_title(target: str) -> str:
    """Drop the leading dot of a suffix target and, after ``~``, all but the last key."""
    if target.startswith("~"):
        return target.rsplit(".", maxsplit=1)[-1]
    return target.lstrip(".")


def _normalize_label(target: str) -> str:
    """Spell the keys of an exact target the way they appear in labels.

    >>> _normalize_label("settings.tool.log_level")
    'settings.tool.log-level'
    >>> _normalize_label("api/config:tool.Server_Port-toml-2")
    'api/config:tool.server-port-toml-2'
    """
    docname, colon, anchor = target.rpartition(":")
    return docname + colon + _make_anchor("", tuple(anchor.split(".")), "")


class _ConfigSchemaDomain(Domain):
    """Resolve references to the keys of a :rst:dir:`config-schema` example.

    The :rst:role:`config-schema:option` role takes the same labels as :rst:role:`ref`,
    but renders the link as inline code and titles it with the key by default. A target
    with a leading dot matches any label whose key path ends with the given keys.
    """

    name = "config-schema"
    label = "Configuration schema"
    roles = {"option": _OptionRole(innernodeclass=nodes.literal, warn_dangling=True)}  # ruff: ignore[mutable-class-default]
    data_version = 1
    initial_data = {"options": {}}  # ruff: ignore[mutable-class-default]

    @property
    def options(self) -> dict[str, tuple[str, str, str, str]]:
        """Document, anchor, key text, and dotted key path per label."""
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
        label = self._find_label(fromdocname, target, node)
        if label is None:
            return None
        docname, anchor, key, _ = self.options[label]
        if node.get("config-schema:short"):
            key = key.rsplit(".", maxsplit=1)[-1]
        if not node.get("refexplicit"):
            contnode = nodes.literal(key, key)
        return make_refnode(builder, fromdocname, docname, anchor, contnode, key)

    def _find_label(
        self, fromdocname: str, target: str, node: pending_xref
    ) -> str | None:
        """Look up a label, or with a leading dot, the labels ending in that key path.

        Among suffix matches, labels in the current document take precedence, then
        labels whose complete key path equals the target.
        """
        if not target.startswith("."):
            label = _normalize_label(target)
            return label if label in self.options else None
        suffix = _make_anchor("", tuple(target[1:].split(".")), "")
        matches = sorted(
            label
            for label, (*_, path) in self.options.items()
            if f".{path}".endswith(f".{suffix}")
        )
        local = [m for m in matches if self.options[m][0] == fromdocname]
        candidates = local or matches
        complete = [c for c in candidates if self.options[c][3] == suffix]
        candidates = complete or candidates
        if len(candidates) > 1:
            _LOGGER.warning(
                "more than one option found for %r: %s",
                target,
                ", ".join(candidates),
                location=node,
                type="ref",
                subtype="option",
            )
        return candidates[0] if candidates else None

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
    app.add_role(
        OPTION_ROLE_ALIAS,
        _OptionRole(innernodeclass=nodes.literal, warn_dangling=True),
    )
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
