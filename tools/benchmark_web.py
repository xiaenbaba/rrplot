"""可重复的编辑器后端基准：python tools/benchmark_web.py --repeat 5。"""

import argparse
import copy
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import matplotlib  # noqa: E402

matplotlib.use("Agg")

from rrplot.scene_renderer import resolve_for_editor  # noqa: E402


def sample_document(count):
    nodes = [
        dict(
            id=f"n{i}",
            type="heat_exchanger",
            x=100 + i % 20 * 180,
            y=100 + i // 20 * 100,
        )
        for i in range(count)
    ]
    edges = [
        dict(
            id=f"e{i}",
            source=dict(nodeId=f"n{i - 1}", portId="right"),
            target=dict(nodeId=f"n{i}", portId="left"),
        )
        for i in range(1, count)
    ]
    return dict(
        schemaVersion=1,
        page=dict(width=4000, height=4000),
        nodes=nodes,
        edges=edges,
        junctions=[],
        labels=[],
    )


def benchmark(count, repeat):
    document = sample_document(count)
    started = time.perf_counter()
    resolve_for_editor(document)
    warmup = (time.perf_counter() - started) * 1000
    samples = []
    for _ in range(repeat):
        changed = copy.deepcopy(document)
        changed["nodes"][count // 2]["x"] += 1
        started = time.perf_counter()
        result = resolve_for_editor(changed)
        samples.append((time.perf_counter() - started) * 1000)
    return dict(
        nodes=count,
        edges=len(document["edges"]),
        warmupMs=round(warmup, 2),
        resolveMedianMs=round(statistics.median(samples), 2),
        responseBytes=len(json.dumps(result).encode()),
        repeat=repeat,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", type=int, nargs="+", default=[50, 200, 500])
    parser.add_argument("--repeat", type=int, default=5)
    args = parser.parse_args()
    if args.repeat < 1 or any(n < 1 or n > 500 for n in args.sizes):
        parser.error("repeat 至少 1，节点数量为 1～500")
    print(
        json.dumps(
            [benchmark(n, args.repeat) for n in args.sizes],
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
