# -*- coding: utf-8 -*-
"""端口/标注的最小回归测试:python tests/test_cycleplot.py 即可跑。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cycleplot import Diagram, parts
from cycleplot.core import Port, _is_sensor, make_partial


def test_evaporator_ports_on_body():
    assert parts.evaporator.port("in") == (0, 48)
    assert parts.evaporator.port("out") == (0, -48)
    assert parts.evaporator.direction("in") == (0, 1)
    assert parts.evaporator.direction("out") == (0, -1)


def test_scroll_discharge_on_circle():
    assert parts.scroll_compressor.port("discharge") == (95, 0)


def test_make_partial_dirs_and_stale_dir_dropped():
    sp = make_partial(parts.make_rect(260, 110),
                      {"vapor_out": (-65, -55)}, dirs={"vapor_out": "n"})
    assert sp.direction("vapor_out") == (0, -1)
    # 挪了端口位置,旧方向声明应作废并回落到按偏移推断
    sp2 = make_partial(parts.evaporator, {"in": (-24, 48), "out": (24, 48)})
    assert sp2.direction("in") == (0, 1)
    assert sp2.direction("out") == (0, 1)


def test_is_sensor_mathtext():
    assert _is_sensor(r"$T_0$")
    assert _is_sensor(r"$P_3$")
    assert _is_sensor("T_1")
    assert not _is_sensor("1")
    assert not _is_sensor("4")


def test_state_dict_not_mutated():
    d = Diagram(width=100, height=100)
    spec = {"text": "1", "at": 0.5}
    d.pipe((0, 0), (50, 50), states=[spec])
    assert spec == {"text": "1", "at": 0.5}


def test_port_repr_with_bare_coordinate():
    assert "Port" in repr(Port((1, 2), (0, 0), None))


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
