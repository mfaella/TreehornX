# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import os
import sys
from typing import get_args


sys.path.insert(0, os.path.abspath("../../src"))

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "TreehornX"
copyright = "2025, Nicola Gentile, Marco Faella, Gennaro Parlato"
author = "Gennaro Parlato, Marco Faella, Nicola Gentile"
release = "0.1.0"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "sphinx_autodoc_typehints",
]

templates_path = ["_templates"]
exclude_patterns = []

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]

# Read the Docs theme options
html_theme_options = {
    "collapse_navigation": True,
    "sticky_navigation": True,
    "navigation_depth": 4,
    "includehidden": False,
    "titles_only": False,
}

# -- Extension configuration -------------------------------------------------

# autodoc settings
autodoc_default_options = {
    "members": True,
    "member-order": "bysource",
    "special-members": "__init__",
    "undoc-members": True,
    "exclude-members": "__weakref__",
}


# Exclude private classes and members from documentation
def autodoc_skip_member(app, what, name, obj, skip, options):
    """Skip private/internal members starting with underscore."""
    # Skip anything starting with underscore (private/internal)
    if name.startswith("_"):
        return True
    return skip


# Napoleon settings (for Google/NumPy style docstrings)
napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = True
napoleon_include_private_with_doc = False
napoleon_include_special_with_doc = True
napoleon_use_admonition_for_examples = False
napoleon_use_admonition_for_notes = False
napoleon_use_admonition_for_references = False
napoleon_use_ivar = False
napoleon_use_param = True
napoleon_use_rtype = True
napoleon_preprocess_types = False
napoleon_type_aliases = None
napoleon_attr_annotations = True

# Intersphinx configuration
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

# Type hints configuration
typehints_use_rtype = False
always_document_param_types = True
typehints_fully_qualified = False
typehints_use_signature = True
typehints_use_signature_return = True

# Configure type aliases to be displayed by their alias names instead of expanded
autodoc_type_aliases = {
    "_BoolExpr": "treehornx.ir.expressions._BoolExpr",
    "_NumExpr": "treehornx.ir.expressions._NumExpr",
    "Expr": "treehornx.ir.expressions.Expr",
}


def setup(app):
    """Sphinx setup function to register custom handlers."""
    app.connect("autodoc-skip-member", autodoc_skip_member)
