"""仅使用标准库核验发布标签、源码及 wheel 元数据的版本一致。"""

import argparse
import ast
import email
import os
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check_release(tag, folder):
    module = ast.parse((ROOT / "rrplot/__init__.py").read_text(encoding="utf-8"))
    version = next(
        ast.literal_eval(node.value)
        for node in module.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "__version__" for t in node.targets)
    )
    if tag != "v" + version:
        raise ValueError(f"发布标签 {tag!r} 与源码版本 v{version} 不一致")
    wheels = list(folder.glob("*.whl"))
    if len(wheels) != 1:
        raise ValueError("发布目录必须恰好包含一个 wheel")
    with zipfile.ZipFile(wheels[0]) as wheel:
        metadata = next(
            n for n in wheel.namelist() if n.endswith(".dist-info/METADATA")
        )
        package = email.message_from_bytes(wheel.read(metadata))
    if package["Name"] != "rrplot" or package["Version"] != version:
        raise ValueError("wheel 元数据与源码版本不一致")
    return version


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default=os.environ.get("GITHUB_REF_NAME", ""))
    parser.add_argument("--dist", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    try:
        version = check_release(args.tag, args.dist)
    except (ValueError, OSError, StopIteration) as exc:
        parser.exit(1, f"发布检查失败：{exc}\n")
    print(f"发布标签、源码和 wheel 版本一致：{version}")


if __name__ == "__main__":
    main()
