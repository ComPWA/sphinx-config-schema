# sphinx-config-schema

[![PyPI package](https://badge.fury.io/py/sphinx-config-schema.svg)](https://pypi.org/project/sphinx-config-schema)
[![Spelling checked](https://img.shields.io/badge/cspell-checked-brightgreen.svg)](https://github.com/streetsidesoftware/cspell/tree/main/packages/cspell)
[![code style: prettier](https://img.shields.io/badge/code_style-prettier-ff69b4.svg?style=flat-square)](https://github.com/prettier/prettier)
[![pre-commit.ci status](https://results.pre-commit.ci/badge/github/ComPWA/sphinx-config-schema/main.svg)](https://results.pre-commit.ci/latest/github/ComPWA/sphinx-config-schema/main)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/charliermarsh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![ty](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ty/main/assets/badge/v0.json)](https://github.com/astral-sh/ty)

`sphinx-config-schema` is a [Sphinx](https://www.sphinx-doc.org) extension that renders a [JSON schema](https://json-schema.org) as a copyable TOML, YAML, or JSON example, with the description of each setting as a tooltip.

```bash
pip install sphinx-config-schema
```

```python
extensions = [
    "sphinx_config_schema",
]
```

````md
```{config-schema} example.schema.json
:caption: pyproject.toml
:table: tool.example
```
````

See [compwa.github.io/sphinx-config-schema](https://compwa.github.io/sphinx-config-schema) for the documentation and a rendered example.
