from __future__ import annotations

from sphinx_api_relink.helpers import (
    get_branch_name,
    get_git_revision,
    get_package_version,
)

BRANCH = get_branch_name()
ORGANIZATION = "ComPWA"
REPO_NAME = "sphinx-toml-schema"
REPO_TITLE = "sphinx-toml-schema"
PACKAGE_NAME = "sphinx_toml_schema"

add_module_names = False
api_github_repo = f"{ORGANIZATION}/{REPO_NAME}"
api_linkcode_rev = get_git_revision()
api_target_substitutions = {"Sphinx": "sphinx.application.Sphinx"}
author = ""
autodoc_default_options = {
    "members": True,
    "undoc-members": True,
    "show-inheritance": True,
}
autodoc_member_order = "bysource"
autodoc_typehints_format = "short"
copybutton_prompt_is_regexp = True
copybutton_prompt_text = r"\$ "
copyright = f"2026, {ORGANIZATION}"
default_role = "py:obj"
extensions = [
    "myst_parser",
    "sphinx.ext.intersphinx",
    "sphinx.ext.napoleon",
    "sphinx_api_relink",
    "sphinx_copybutton",
    "sphinx_design",
    "sphinx_toml_schema",
]
generate_apidoc_package_path = f"../src/{PACKAGE_NAME}"
html_context = {
    "doc_path": "docs",
    "github_repo": REPO_NAME,
    "github_user": ORGANIZATION,
    "github_version": BRANCH,
}
html_favicon = "_static/favicon.ico"
html_last_updated_fmt = "%-d %B %Y"
html_logo = (
    "https://raw.githubusercontent.com/ComPWA/ComPWA/04e5199/doc/images/logo.svg"
)
html_sidebars = {"**": []}
html_show_copyright = False
html_show_sourcelink = False
html_show_sphinx = False
html_static_path = ["_static"]
html_theme = "pydata_sphinx_theme"
html_theme_options = {
    "icon_links": [
        {
            "name": "Common Partial Wave Analysis",
            "url": "https://compwa.github.io",
            "icon": "_static/favicon.ico",
            "type": "local",
        },
        {
            "name": "GitHub",
            "url": f"https://github.com/{ORGANIZATION}/{REPO_NAME}",
            "icon": "fa-brands fa-github",
        },
    ],
    "footer_end": [],
    "logo": {"text": REPO_TITLE},
    "navbar_align": "right",
    "navigation_with_keys": False,
    "secondary_sidebar_items": ["page-toc", "edit-this-page"],
    "show_prev_next": False,
    "show_toc_level": 2,
    "use_edit_page_button": True,
}
html_title = REPO_TITLE
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "sphinx": ("https://www.sphinx-doc.org/en/master", None),
}
myst_heading_anchors = 2
myst_enable_extensions = [
    "colon_fence",
]
nitpick_ignore = [
    ("py:class", "docutils.nodes.Element"),
    ("py:class", "docutils.nodes.Node"),
]
nitpicky = True
project = REPO_TITLE
release = get_package_version(PACKAGE_NAME)
tippy_anchor_parent_selector = "article.bd-article"
tippy_props = {
    "delay": [200, 100],
    "maxWidth": 500,
    "placement": "auto-start",
}
version = get_package_version(PACKAGE_NAME)
