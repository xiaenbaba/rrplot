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

for _name in ("core", "parts", "hvac", "style", "svgparts", "_primitives"):
    sys.modules[f"{__name__}.{_name}"] = importlib.import_module(
        f"rrplot.{_name}"
    )

from rrplot import *  # noqa: F401,F403,E402

__version__ = _rrplot.__version__
