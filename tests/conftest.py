"""CI 的 JavaScript 运行时属于必需验证条件，不得静默跳过。"""

import os
import shutil

import pytest


def pytest_sessionstart(session):
    if os.environ.get("RRPLOT_REQUIRE_NODE") == "1" and not shutil.which("node"):
        raise pytest.UsageError(
            "RRPLOT_REQUIRE_NODE=1，但找不到 Node.js；请先配置 Node。"
        )
