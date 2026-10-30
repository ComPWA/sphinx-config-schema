from sphinx_api_relink.helpers import (
    get_branch_name,
    get_git_revision,
    get_package_version,
)

BRANCH = get_branch_name()
REVISION = get_git_revision()
ORGANIZATION = "ComPWA"
REPO_NAME = "sphinx-config-schema"
PACKAGE_NAME = REPO_NAME.replace("-", "_")

add_module_names = False
api_github_repo = f"{ORGANIZATION}/{REPO_NAME}"
api_linkcode_rev = REVISION
api_target_substitutions = {"Sphinx": "sphinx.application.Sphinx"}
autodoc_default_options = {
    "members": True,
    "undoc-members": True,
    "show-inheritance": True,
}
autodoc_member_order = "bysource"
autodoc_typehints_format = "short"
codeautolink_concat_default = True
codeautolink_global_preface = f"from {PACKAGE_NAME} import *"
default_role = "py:obj"
extensions = [
    "myst_parser",
    "sphinx_api_relink",
    "sphinx_codeautolink",
    "sphinx_config_schema",
    "sphinx_copybutton",
    "sphinx_design",
    "sphinx.ext.intersphinx",
    "sphinx.ext.napoleon",
]
generate_apidoc_package_path = f"../src/{PACKAGE_NAME}"
html_context = {
    "doc_path": "docs",
    "github_repo": REPO_NAME,
    "github_user": ORGANIZATION,
    "github_version": BRANCH,
    "github_view_rev": REVISION,
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
    "logo": {"text": REPO_NAME},
    "navbar_align": "right",
    "navigation_with_keys": False,
    "secondary_sidebar_items": [
        "page-toc",
        "edit-this-page",
        "view-on-github",
    ],
    "show_prev_next": False,
    "show_toc_level": 2,
    "use_edit_page_button": True,
}
html_title = REPO_NAME
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "sphinx": ("https://www.sphinx-doc.org/en/master", None),
}
myst_enable_extensions = [
    "colon_fence",
    "substitution",
]
myst_substitutions = {
    "example_schema": (
        f"[example schema](https://github.com/{ORGANIZATION}/{REPO_NAME}/blob/{REVISION}/docs/example.schema.json)"
    ),
}
nitpick_ignore = [
    ("py:class", "docutils.nodes.Element"),
    ("py:class", "docutils.nodes.Node"),
]
nitpicky = True
project = REPO_NAME
release = get_package_version(PACKAGE_NAME)
templates_path = ["_templates"]
tippy_anchor_parent_selector = "article.bd-article"
tippy_props = {
    "delay": [200, 100],
    "maxWidth": 500,
    "placement": "auto-start",
}
toc_object_entries = False
version = get_package_version(PACKAGE_NAME)
