# sphinx-config-schema

[![License](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![PyPI package](https://badge.fury.io/py/sphinx-config-schema.svg)](https://pypi.org/project/sphinx-config-schema)
[![Supported Python versions](https://img.shields.io/pypi/pyversions/sphinx-config-schema)](https://pypi.org/project/sphinx-config-schema)

[![pre-commit.ci status](https://results.pre-commit.ci/badge/github/ComPWA/sphinx-config-schema/main.svg)](https://results.pre-commit.ci/latest/github/ComPWA/sphinx-config-schema/main)
[![CI status](https://github.com/ComPWA/sphinx-config-schema/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/ComPWA/sphinx-config-schema/actions/workflows/ci.yml?query=branch%3Amain)
[![Spelling checked](https://img.shields.io/badge/cspell-checked-brightgreen.svg)](https://github.com/streetsidesoftware/cspell/tree/main/packages/cspell)
[![code style: prettier](https://img.shields.io/badge/code_style-prettier-ff69b4.svg?style=flat-square)](https://github.com/prettier/prettier)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/charliermarsh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![ty](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ty/main/assets/badge/v0.json)](https://github.com/astral-sh/ty)

`sphinx-config-schema` is a [Sphinx](https://www.sphinx-doc.org) extension that renders a [JSON schema](https://json-schema.org) as a copyable TOML, YAML, or JSON example. Each key shows the description of its setting as a tooltip and links to itself as a permalink.

```bash
pip install sphinx-config-schema
```

Then add the extension to your `conf.py`:

```python
extensions = [
    "sphinx_config_schema",
]
```

and render a schema in a MyST page:

````md
```{config-schema} example.schema.json
:caption: pyproject.toml
:table: tool.example
:format: toml
```
````

See [compwa.github.io/sphinx-config-schema](https://compwa.github.io/sphinx-config-schema) for the documentation and a rendered example.
