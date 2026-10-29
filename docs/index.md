# sphinx-config-schema

:::{title} Welcome
:::

`sphinx-config-schema` is a [Sphinx](https://www.sphinx-doc.org) extension that renders a [JSON schema](https://json-schema.org) as a copyable TOML, YAML, or JSON example. Each key in the example shows the description of that setting as a tooltip, via [`sphinx-tippy`](https://github.com/sphinx-extensions2/sphinx-tippy), and links to itself so that it can be shared as a permalink.

This is useful for tools that read their configuration from a file, such as a `[tool.*]` table in `pyproject.toml`, and that generate a JSON schema for it, for instance for editor completion.

## Installation

```bash
pip install sphinx-config-schema
```

Then add the extension to your `conf.py`. It loads `sphinx_tippy` automatically:

```python
extensions = [
    "sphinx_config_schema",
]
```

## Usage

The {rst:dir}`config-schema` directive takes the path to a JSON schema file, relative to the current document or, with a leading `/`, to the documentation source directory. The optional {rst:dir}`table <config-schema:table>` option sets the dotted path of the table under which the settings appear, {rst:dir}`caption <config-schema:caption>` adds a caption to the code block, and {rst:dir}`format <config-schema:format>` selects the output format:

:::::{tab-set}

::::{tab-item} MyST
:sync: myst

````md
```{config-schema} example.schema.json
:caption: pyproject.toml
:table: tool.example
:format: toml
```
````

::::

::::{tab-item} reST
:sync: rst

```rst
.. config-schema:: example.schema.json
    :caption: pyproject.toml
    :table: tool.example
    :format: toml
```

::::

:::::

The {rst:dir}`format <config-schema:format>` option renders the example as `yaml` or `json` instead of the default `toml`. Settings are then nested by indentation instead of grouped under table headers. The tabs below show the same schema in each format. Hover over a key to see what it does:

::::{tab-set}

:::{tab-item} TOML

```{config-schema} example.schema.json
:caption: pyproject.toml
:table: tool.example
```

:::

:::{tab-item} YAML

```{config-schema} example.schema.json
:caption: config.yaml
:format: yaml
```

:::

:::{tab-item} JSON

```{config-schema} example.schema.json
:caption: config.json
:format: json
```

:::

::::

Each setting shows its `default` or, if it has none, its first entry in `examples`. An empty list or table counts as no default, because it is usually a placeholder. Settings with neither are left out, or reported as an error with the {rst:dir}`strict <config-schema:strict>` flag, which helps to keep a schema complete. Objects with their own `properties` become nested tables, also when they are a local `$ref` such as the ones that [pydantic](https://docs.pydantic.dev) generates.

The tooltip of a key shows the `description` of the setting, or of the schema itself for the last part of the {rst:dir}`table <config-schema:table>`, with ` ``code`` ` rendered as code, followed by its allowed values if it has an `enum` and any examples that the code block does not show. When the same key appears more than once on a page, as in the tabs above, the later anchors get the format as a suffix, such as `#tool-example-output-yaml`, so that each permalink stays unique.

The example is built from regular docutils nodes, so it also appears in other output formats, such as LaTeX and plain text. There, each key becomes a label that can be referenced.

The tooltips use the colors of the [PyData Sphinx Theme](https://pydata-sphinx-theme.readthedocs.io) and its derivatives where available, so that they follow light and dark mode.

## Reference

````{rst:directive} .. config-schema:: path
Render the JSON schema at `path` as a configuration example. The path is relative to the current document or, with a leading `/`, to the documentation source directory.

```{rst:directive:option} caption: text
:type: text

Caption of the code block, typically the name of the configuration file.
```

```{rst:directive:option} format: toml, yaml or json
:type: ``toml`` (default), ``yaml`` or ``json``

Serialization format of the example.
```

```{rst:directive:option} strict
:type: flag

Report settings that have neither a `default` nor `examples` as an error instead of leaving them out.
```

```{rst:directive:option} table: dotted.path
:type: text

Dotted path of the table under which the settings appear, such as `tool.example`.
```
````

```{toctree}
:hidden:
API <api/sphinx_config_schema>
Changelog <https://github.com/ComPWA/sphinx-config-schema/releases>
```
