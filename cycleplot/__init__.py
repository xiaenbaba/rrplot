# -*- coding: utf-8 -*-
"""Compatibility alias for projects that imported the former ``cycleplot`` name."""
import importlib
import sys
import warnings

import rrplot as _rrplot

warnings.warn(
    "cycleplot is deprecated; use rrplot instead",
    DeprecationWarning,
    stacklevel=2,
)

for _name in (
    "core",
    "part",
    "parts",
    "hvac",
    "style",
    "svgparts",
    "registry",
    "scene",
    "scene_renderer",
    "_primitives",
):
    _mod = importlib.import_module(f"rrplot.{_name}")
    sys.modules[f"{__name__}.{_name}"] = _mod
    globals()[_name] = _mod

from rrplot import *  # noqa: F401,F403,E402

__version__ = _rrplot.__version__
