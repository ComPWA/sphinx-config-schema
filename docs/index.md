# sphinx-toml-schema

:::{title} Welcome
:::

`sphinx-toml-schema` is a [Sphinx](https://www.sphinx-doc.org) extension that renders a [JSON schema](https://json-schema.org) as a copyable TOML example. Each key in the example shows the description of that setting as a tooltip, via [`sphinx-tippy`](https://github.com/sphinx-extensions2/sphinx-tippy), and links to itself so that it can be shared as a permalink.

This is useful for tools that read their configuration from a TOML file, such as a `[tool.*]` table in `pyproject.toml`, and that generate a JSON schema for it, for instance for editor completion.

## Installation

```bash
pip install sphinx-toml-schema
```

Then add the extension to your `conf.py`. It loads `sphinx_tippy` automatically:

```python
extensions = [
    "sphinx_toml_schema",
]
```

## Usage

The `toml-schema` directive takes the path to a JSON schema file, relative to the current document or, with a leading `/`, to the documentation source directory. The optional `table` option sets the TOML table under which the settings appear and `caption` adds a caption to the code block:

````md
```{toml-schema} example.schema.json
:caption: pyproject.toml
:table: tool.example
```
````

This renders as follows. Hover over a key to see what it does:

```{toml-schema} example.schema.json
:caption: pyproject.toml
:table: tool.example
```

The example shows every setting with its `default` or, if there is none, its first entry in `examples`. An empty list or table as `default` also gives way to an example, because it is usually a placeholder. Settings with neither are left out, unless the `strict` flag is set, in which case the directive reports them as an error. This helps to keep the schema complete, for instance by requiring an `examples` entry for every setting without a default. Nested `object` properties with their own `properties` become TOML sub-tables, also when they are a local `$ref`, such as the `#/$defs/...` references that [pydantic](https://docs.pydantic.dev) generates. Descriptions can contain inline literals as ` ``code`` `, which is what descriptions generated from Python docstrings typically use.

The example is built from regular docutils nodes, so it also appears in other output formats, such as LaTeX and plain text. There, each key becomes a label that can be referenced.

The tooltips use the colors of the [PyData Sphinx Theme](https://pydata-sphinx-theme.readthedocs.io) and its derivatives where available, so that they follow light and dark mode.

```{toctree}
:hidden:
API <api/sphinx_toml_schema>
Changelog <https://github.com/ComPWA/sphinx-toml-schema/releases>
```
