"""Sphinx 配置 — rrplot 项目文档.

构建命令: sphinx-build -b html docs docs/_build/html
"""

from __future__ import annotations

import sys
from pathlib import Path

# 将项目根加入 sys.path, 使 autodoc 能 import rrplot
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rrplot import __version__  # noqa: E402

project = "rrplot"
author = "xiaenbaba"
copyright = "2026, xiaenbaba"  # noqa: A001  # Sphinx 约定的模块级变量名, 不可改名
release = __version__

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# 中文文档
language = "zh_CN"

# 主题
html_theme = "sphinx_rtd_theme"

# autodoc 行为
autodoc_member_order = "bysource"
autodoc_typehints = "description"
autodoc_typehints_description_target = "documented"
autodoc_inherit_docstrings = False
autodoc_default_options = {
    "members": True,
    "undoc-members": True,
    "show-inheritance": True,
}

# napoleon: Google docstring 风格 (项目统一使用 Args:/Returns:)
napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_include_private_with_doc = False

# intersphinx 交叉引用
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "matplotlib": ("https://matplotlib.org/stable", None),
}
