# -*- coding: utf-8 -*-
"""端口/标注的最小回归测试:python tests/test_cycleplot.py 即可跑。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cycleplot import Diagram, parts
from cycleplot.core import Port, _is_sensor, make_partial
from cycleplot.svgparts import load_svg_part


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


def test_pipe_records_color():
    d = Diagram(width=100, height=100)
    p = d.pipe((0, 0), (50, 0), color="#e53935")
    assert p.color == "#e53935"
    assert p.points() == [(0.0, 0.0), (50.0, 0.0)]


def test_load_svg_part_moves_override_port():
    sym = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "references", "hvacsvg", "symbols", "04_蓄热水箱.svg")
    p = load_svg_part(sym, scale=1.5, moves={"right": (160, 72)})
    # 口挪到 (160, 72):偏移 = (x - cx, y - cy) * scale
    assert p.port("right") == (120.0, 33.0)
    # 未覆盖的口不受影响
    assert p.port("upper") == (-120.0, -27.0)


def test_load_svg_part_ports_and_rename():
    sym = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "references", "hvacsvg", "symbols", "02_水泵.svg")
    p = load_svg_part(sym, ports={"in": "suction", "out": "discharge"})
    assert p.name == "水泵"
    assert p.port("suction") == (-80.0, 0.0)
    assert p.port("discharge") == (80.0, 0.0)
    assert p.direction("suction") == (-1, 0)
    # 同一符号换 scale,端口偏移按比例缩放
    p2 = load_svg_part(sym, scale=0.5)
    assert p2.port("in") == (-40.0, 0.0)


def test_hvac_factory_ports_match_svg_part():
    """hvac 代码图元与 load_svg_part 的端口定义保持一致。"""
    from cycleplot import hvac
    sym_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "references", "hvacsvg", "symbols")
    for svg, factory in [("04_蓄热水箱.svg", hvac.thermal_tank),
                         ("01_空气能主机.svg", hvac.heat_pump),
                         ("13_分水器_供.svg", hvac.supply_manifold)]:
        ref = load_svg_part(os.path.join(sym_dir, svg), scale=1.5,
                            moves={"right": (160, 72), "main": (25, 50)})
        nat = factory(scale=1.5, moves={"right": (160, 72), "main": (25, 50)})
        assert nat.name == ref.name
        assert set(nat.ports) == set(ref.ports)
        for k in nat.ports:
            assert nat.port(k) == ref.port(k), (svg, k)
            assert nat.direction(k) == ref.direction(k)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
