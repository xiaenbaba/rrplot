# -*- coding: utf-8 -*-
"""Sphinx 构建配置:本地执行 sphinx-build -b html docs docs/_build/html。"""
import os
import sys

sys.path.insert(0, os.path.abspath(".."))

project = "cycleplot"
copyright = "2026, xiaenbaba"
author = "xiaenbaba"
release = "0.1.0"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
]

exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

language = "zh_CN"

html_theme = "alabaster"

autodoc_member_order = "bysource"
autodoc_inherit_docstrings = False
autodoc_default_options = {
    "members": True,
    "undoc-members": True,
    "show-inheritance": True,
}
