# -*- coding: utf-8 -*-
"""端口/标注的最小回归测试:python tests/test_rrplot.py 即可跑。"""
import os
import sys

import matplotlib

matplotlib.use("Agg")            # 无界面环境稳定出图
import matplotlib.pyplot as plt  # noqa: E402  须在 use() 之后导入

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rrplot import Diagram, parts
from rrplot.core import (
    Port,
    _fit_end,
    _is_sensor,
    _orthogonalize,
    _resolve_at,
    make_partial,
)
from rrplot.svgparts import load_svg_part

try:
    import pytest
except ImportError:                      # 直跑模式无 pytest,fixture 跳过
    pytest = None
else:
    @pytest.fixture(autouse=True)
    def _close_figures():
        """每例结束清空 figure,避免套件累积超 matplotlib 上限告警。"""
        yield
        plt.close("all")


def _raises(exc, fn, *args, **kw):
    """兼容 pytest 与 `python tests/test_rrplot.py` 两种跑法的断言。"""
    try:
        fn(*args, **kw)
    except exc as e:
        return e
    raise AssertionError(f"未抛出 {exc.__name__}")


def test_heat_exchanger_ports_on_body():
    hx = parts.make_heat_exchanger(48, 96)
    assert hx.port("top") == (0, -48)
    assert hx.port("bottom") == (0, 48)
    assert hx.direction("top") == (0, -1)
    assert hx.direction("bottom") == (0, 1)


def test_compressor_style_factory_ports():
    """圆形/方形共用几何口;制冷口是 top/bottom/right 的别名。"""
    round_ = parts.make_compressor(style="圆形")
    assert round_.port("top") == (0, -95)
    assert round_.port("bottom") == (0, 95)
    assert round_.port("left") == (-95, 0)
    assert round_.port("suction") == round_.port("top")
    assert round_.port("discharge") == round_.port("bottom")
    assert round_.port("vapor_inj") == round_.port("right")
    cap = parts.make_compressor(style="方形")
    assert cap.port("top") == (0, -95)
    assert cap.port("bottom") == (0, 95)
    assert cap.port("left") == (-47.5, 0)
    assert cap.port("right") == (47.5, 0)
    assert cap.port("vapor_inj") == cap.port("right")
    assert parts.compressor.port("suction") == (0, -95)
    assert parts.compressor.port("discharge") == (0, 95)
    assert parts.compressor.port("top") == parts.compressor.port("suction")
    e = _raises(ValueError, parts.make_compressor, style="scroll")
    assert "style" in str(e) and "圆形" in str(e)


def test_make_partial_dirs_and_stale_dir_dropped():
    sp = make_partial(parts.make_heat_exchanger(260, 110),
                      {"vapor_out": (-65, -55)}, dirs={"vapor_out": "n"})
    assert sp.direction("vapor_out") == (0, -1)
    # 挪了端口位置,旧方向声明应作废并回落到按偏移推断
    sp2 = make_partial(parts.make_heat_exchanger(48, 96),
                       {"left": (-24, 48), "right": (24, 48)})
    assert sp2.direction("left") == (0, 1)
    assert sp2.direction("right") == (0, 1)


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


def test_pipe_records_linestyle():
    d = Diagram(width=100, height=100)
    p = d.pipe((0, 0), (50, 0), linestyle="dashed")
    assert p.linestyle == "dashed"
    p2 = d.pipe((0, 10), (50, 10))
    assert p2.linestyle == "solid"
    d.render()


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


def test_load_svg_part_rejects_unsafe_xml():
    """外部 SVG 的 DTD/实体声明必须被拒绝。"""
    import tempfile

    fd, path = tempfile.mkstemp(suffix=".svg")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(
                '<!DOCTYPE svg [<!ENTITY xxe "blocked">]>'
                '<svg viewBox="0 0 10 10" data-connection-points="[]" />'
            )
        err = _raises(ValueError, load_svg_part, path)
        assert "DOCTYPE" in str(err)
    finally:
        os.unlink(path)


def test_hvac_factory_ports_match_svg_part():
    """hvac 代码图元与 load_svg_part 的端口定义保持一致。"""
    from rrplot import hvac
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


def _port(point, direction):
    d = {"e": (1, 0), "w": (-1, 0), "n": (0, -1), "s": (0, 1)}[direction]
    return Port(point, d, None)


def test_fit_end_snap_small_tangent_offset():
    # 东向端口 + 邻段切向 8px 错位:吸附到沿法向的笔直切入,返回 None
    pts = [(100.0, 50.0), (108.0, 0.0), (170.0, 0.0)]
    assert _fit_end(pts, True, _port((100.0, 50.0), "e")) is None
    assert pts[1] == (100.0, 0.0)
    assert pts[0] == (100.0, 50.0)


def test_fit_end_big_offset_normal_side_returns_hint():
    # 斜接且错位大、在法向正确一侧:不改坐标,返回走线提示给 _orthogonalize
    pts = [(100.0, 50.0), (300.0, 30.0)]
    assert _fit_end(pts, True, _port((100.0, 50.0), "e")) == "h"
    assert pts == [(100.0, 50.0), (300.0, 30.0)]
    # 东向端口但来点在背面:提示为 None(交给走线提示以外的常规规则)
    pts = [(100.0, 50.0), (80.0, 30.0)]
    assert _fit_end(pts, True, _port((100.0, 50.0), "e")) is None


def test_fit_end_tangent_aligned_backside_snapped():
    # 切向对齐但来点在端口法向背面近处:整段吸附到端口坐标
    pts = [(100.0, 50.0), (96.0, 50.0)]
    assert _fit_end(pts, True, _port((100.0, 50.0), "e")) is None
    assert pts[1] == (100.0, 50.0)
    # 终点端:连 feeder 竖段一起挪到端口平面
    pts = [(50.0, 300.0), (50.0, 70.0), (50.0, 60.0)]
    assert _fit_end(pts, False, _port((50.0, 60.0), "n")) is None
    assert pts[1] == (50.0, 60.0)


def test_orthogonalize_inserts_corner():
    assert _orthogonalize([(0.0, 0.0), (108.0, 30.0)]) == \
        [(0.0, 0.0), (0.0, 30.0), (108.0, 30.0)]


def test_orthogonalize_first_and_last_along():
    # first_along="h":起点先沿水平(东向端口法向)
    assert _orthogonalize([(0.0, 0.0), (108.0, 30.0)], "h") == \
        [(0.0, 0.0), (108.0, 0.0), (108.0, 30.0)]
    # last_along="v":末段竖直(利于终点端口沿法向出入)
    assert _orthogonalize([(0.0, 0.0), (108.0, 30.0)], None, "v") == \
        [(0.0, 0.0), (108.0, 0.0), (108.0, 30.0)]
    assert _orthogonalize([(0.0, 0.0), (30.0, 80.0)], None, "h") == \
        [(0.0, 0.0), (0.0, 80.0), (30.0, 80.0)]


def test_pipe_points_orthogonal_and_cached():
    d = Diagram(width=200, height=200)
    p = d.pipe((0.0, 0.0), (50.0, 50.0))
    assert p.points() == [(0.0, 0.0), (0.0, 50.0), (50.0, 50.0)]
    assert p.points() is p.points()


def test_pipe_via_tokens_end_on_port():
    d = Diagram(width=800, height=600, default_step=100)
    from rrplot import parts as _parts
    comp = d.add(_parts.compressor, None, loc=(330, 140))
    hx = d.add(_parts.make_heat_exchanger(96, 48), None, loc=(100, 105))
    assert d.pipe(hx["top"], comp["suction"],
                  via=[("e", 200), ("n", 105)]).points()[-1] == \
        comp["suction"].point


def test_four_way_round_ports():
    assert parts.four_way_round.port("exhaust") == (0, -40)
    assert parts.four_way_round.port("condenser") == (40, 0)
    assert parts.four_way_round.port("evaporator") == (0, 40)
    assert parts.four_way_round.port("suction") == (-40, 0)
    # 工厂缩放:端口随 r 缩放,默认实例与工厂默认一致
    fw = parts.make_four_way_round(r=30, mark=False)
    assert fw.port("exhaust") == (0, -30)
    assert fw.port("condenser") == (30, 0)
    assert fw.port("evaporator") == (0, 30)
    assert fw.port("suction") == (-30, 0)
    assert fw.direction("exhaust") == (0, -1)
    assert fw.direction("condenser") == (1, 0)
    assert fw.direction("evaporator") == (0, 1)
    assert fw.direction("suction") == (-1, 0)
    d = Diagram(width=300, height=200)
    d.add(fw, "", loc=(150, 100))
    d.render()
    # add() 时 mark=False 可覆盖工厂默认:无内置 D/S/C/E 文字,也不画标签
    assert not d.ax.texts


def test_add_does_not_override_factory_geometry():
    """add() 只能改外观(mark/actuator),不能改工厂锁定的半径/宽度。"""
    fw = parts.make_four_way_round(r=40)
    d = Diagram(width=300, height=200)
    d.add(fw, "", loc=(150, 100), r=60, mark=False)
    d.render()
    assert fw.port("exhaust") == (0, -40)
    assert d.ax.patches[0].get_radius() == 40
    plt.close(d.fig)

    bare = Diagram(width=160, height=120)
    bare.add(parts.bowtie_valve, "", loc=(80, 60), w=200, actuator="none")
    bare.render()
    assert parts.bowtie_valve.port("in") == (38, 0)
    xs = bare.ax.patches[0].get_xy()[:, 0]
    assert max(xs) - min(xs) == 76 / 2
    plt.close(bare.fig)

    d3 = Diagram(width=200, height=200)
    d3.add(parts.compressor, "", loc=(100, 100), r=40, style="方形")
    d3.render()
    assert parts.compressor.port("suction") == (0, -95)
    assert d3.ax.patches[0].get_radius() == 95
    plt.close(d3.fig)


def test_four_way_round_add_time_mark_override():
    """add() 时同名词覆盖工厂默认(mark=False 关闭口别字母)。"""
    d = Diagram(width=300, height=200)
    d.add(parts.four_way_round, "", loc=(150, 100), mark=False)
    d.render()
    assert not d.ax.texts
    d2 = Diagram(width=300, height=200)
    d2.add(parts.four_way_round, "", loc=(150, 100))
    d2.render()
    assert len(d2.ax.texts) == 4          # 内置 D/S/C/E


def test_vessel_ports():
    # 默认 w=66 h=150:rx=33, vapor 在筒体上端右侧(body_top + 4)
    assert parts.vessel.port("top") == (0, -75)
    assert parts.vessel.port("bottom") == (0, 75)
    assert parts.vessel.port("left") == (-33, 0)
    assert parts.vessel.port("vapor") == (33, -38)
    assert parts.vessel.direction("top") == (0, -1)
    assert parts.vessel.direction("bottom") == (0, 1)


def test_intermediate_hex_ports():
    """中间换热器:主路下侧、副路上侧,四口关于中心对称(逆流布置)。"""
    hx = parts.make_intermediate_hex(w=190, h=80, drop=0.275)
    assert hx.port("main_in") == (-95, 22)
    assert hx.port("main_out") == (95, 22)
    assert hx.port("sub_in") == (95, -22)
    assert hx.port("sub_out") == (-95, -22)
    assert hx.direction("main_in") == (-1, 0)
    assert hx.direction("main_out") == (1, 0)
    assert hx.direction("sub_in") == (1, 0)
    assert hx.direction("sub_out") == (-1, 0)
    d = Diagram(width=300, height=140)
    d.add(parts.intermediate_hex, "中间换热器", loc=(150, 70))
    d.render()


def test_vertical_intermediate_hex_channels_and_ports():
    """竖直图元的通道接在上下端口,两路逆流且端口法向朝外。"""
    hx = parts.make_intermediate_hex(w=120, h=240, drop=0.25, orient="v")
    assert hx.port("main_in") == (30, -120)
    assert hx.port("main_out") == (30, 120)
    assert hx.port("sub_in") == (-30, 120)
    assert hx.port("sub_out") == (-30, -120)
    assert hx.direction("main_in") == hx.direction("sub_out") == (0, -1)
    assert hx.direction("main_out") == hx.direction("sub_in") == (0, 1)

    with Diagram(width=300, height=320) as d:
        node = d.add(hx, None, loc=(150, 160))
        d.render()
        shell = d.ax.patches[0]
        assert shell.get_width() == 120
        assert shell.get_height() == 240
        for channel, keys in zip(d.ax.lines, (("main_in", "main_out"),
                                              ("sub_in", "sub_out"))):
            endpoints = list(zip(channel.get_xdata(), channel.get_ydata()))
            assert endpoints == [node[key].point for key in keys]

    _raises(ValueError, parts.make_intermediate_hex, orient="diagonal")


def test_globe_valve_ports():
    # 默认 w=64:接管外端 x=±(32+12)
    assert parts.globe_valve.port("in") == (-44, 0)
    assert parts.globe_valve.port("out") == (44, 0)
    assert parts.globe_valve.direction("in") == (-1, 0)
    assert parts.globe_valve.direction("out") == (1, 0)


def test_solenoid_valve_ports():
    # 默认 r=34:接管外端 x=±(34+12)
    assert parts.solenoid_valve.port("in") == (-46, 0)
    assert parts.solenoid_valve.port("out") == (46, 0)
    assert parts.solenoid_valve.direction("in") == (-1, 0)
    assert parts.solenoid_valve.direction("out") == (1, 0)


def test_expansion_valve_eng_ports():
    """工程画法电子膨胀阀:电磁阀体去掉引线与横杠,端口同电磁阀。"""
    v = parts.expansion_valve_eng
    assert v.port("in") == (-46, 0)
    assert v.port("out") == (46, 0)
    assert v.direction("in") == (-1, 0)
    assert v.direction("out") == (1, 0)


def test_check_valve_ports():
    """单向阀:实心三角 + 尖端挡条,point 决定指向与进出端口。"""
    cv = parts.check_valve
    assert cv.port("in") == (-40, 0)       # 默认 w=56 stub=12
    assert cv.port("out") == (40, 0)
    assert cv.direction("in") == (-1, 0)
    assert cv.direction("out") == (1, 0)
    cw = parts.check_valve_w
    assert cw.port("in") == (40, 0)
    assert cw.port("out") == (-40, 0)
    assert cw.direction("in") == (1, 0)
    assert cw.direction("out") == (-1, 0)
    assert cw.name == "单向阀(反向)"
    e = _raises(ValueError, parts.make_check_valve, point="n")
    assert "point" in str(e) and "'e'" in str(e)


def test_check_valve_render_both_directions():
    d = Diagram(width=360, height=140)
    d.add(parts.check_valve, "单向阀", loc=(90, 70))
    d.add(parts.check_valve_w, "反向", loc=(260, 70))
    d.render()


def test_expansion_valve_x_ports():
    """圆X膨胀阀:端口落圆周,orient 决定水平/竖直与进出方向。"""
    xv = parts.make_expansion_valve_x(orient="h")
    assert xv.port("in") == (-10, 0)
    assert xv.port("out") == (10, 0)
    assert xv.direction("in") == (-1, 0)
    assert xv.direction("out") == (1, 0)
    vv = parts.make_expansion_valve_x(orient="v")
    assert vv.port("in") == (0, -10)
    assert vv.port("out") == (0, 10)
    assert vv.direction("in") == (0, -1)
    assert vv.direction("out") == (0, 1)
    assert parts.expansion_valve_x.port("in") == (-10, 0)
    e = _raises(ValueError, parts.make_expansion_valve_x, orient="x")
    assert "orient" in str(e) and "'h'" in str(e)


def test_expansion_valve_x_render_both_orients():
    d = Diagram(width=420, height=160)
    d.add(parts.make_expansion_valve_x(orient="h"), "水平", loc=(110, 80))
    d.add(parts.make_expansion_valve_x(orient="v"), "竖直", loc=(300, 80))
    d.render()


def test_filter_ports():
    """过滤器:矩形 + 菱形网格,in=西口 / out=东口。"""
    f = parts.filter
    assert f.port("in") == (-48, 0)       # 默认 w=72 stub=12
    assert f.port("out") == (48, 0)
    assert f.direction("in") == (-1, 0)
    assert f.direction("out") == (1, 0)
    d = Diagram(width=240, height=140)
    d.add(parts.filter, "过滤器", loc=(120, 70))
    d.render()


def test_bowtie_valve_family():
    # 默认 w=76:端口在两三角竖边 x=±38,流向惯例 in=东口/out=西口
    assert parts.bowtie_valve.port("in") == (38, 0)
    assert parts.bowtie_valve.port("out") == (-38, 0)
    assert parts.bowtie_valve.direction("in") == (1, 0)
    assert parts.bowtie_valve.direction("out") == (-1, 0)
    assert parts.bowtie_valve_dome.name == "膨胀阀(穹顶)"
    assert parts.bowtie_valve_solenoid.name == "电磁阀(对顶三角)"
    e = _raises(ValueError, parts.make_bowtie_valve, actuator="gate")
    assert "actuator" in str(e) and "none" in str(e)


def test_bowtie_valve_actuator_override_render():
    # actuator 可在 add() 时以同名词覆盖;三种执行机构都能渲染
    d = Diagram(width=320, height=140)
    d.add(parts.bowtie_valve, "阀", loc=(60, 70))
    d.add(parts.bowtie_valve, "", loc=(160, 70), actuator="dome")
    d.add(parts.bowtie_valve_solenoid, "", loc=(260, 70))
    d.render()
    # 覆盖必须真实生效:裸阀无执行机构线条,dome 多出阀杆 + 穹顶两条
    bare = Diagram(width=120, height=120)
    bare.add(parts.bowtie_valve, "", loc=(60, 60))
    bare.render()
    assert not bare.ax.lines
    domed = Diagram(width=120, height=120)
    domed.add(parts.bowtie_valve, "", loc=(60, 60), actuator="dome")
    domed.render()
    assert len(domed.ax.lines) == 2
    teed = Diagram(width=120, height=120)
    teed.add(parts.bowtie_valve_tee, "", loc=(60, 60))
    teed.render()
    assert len(teed.ax.lines) == 2


def test_oil_separator_ports():
    """油分离器(瘦长矩形壳):侧口进气 / 顶口出气 / 底回油。"""
    oil = parts.oil_separator
    assert oil.port("top") == (0, -104)      # 默认 w=64 h=176 stub=16
    assert oil.port("left") == (-48, -44)    # 侧管在壳顶下 h/4
    assert oil.port("bottom") == (0, 104)
    assert oil.direction("top") == (0, -1)
    assert oil.direction("left") == (-1, 0)
    assert oil.direction("bottom") == (0, 1)


def test_separator_utube_ports():
    """U 形管气液分离器:壳顶短管进气 / U 形管右腿出气 / 弯底放油。"""
    sep = parts.separator_utube
    xin, yin = sep.port("in")
    xout, yout = sep.port("out")
    xd, yd = sep.port("drain")
    assert (round(xin, 1), yin) == (-43.8, -75.0)   # 默认 w=120 stub=16
    assert (round(xout, 1), yout) == (52.2, -75.0)
    assert (xd, round(yd, 1)) == (0, 54.6)          # 弯底放油点
    assert sep.direction("in") == (0, -1)
    assert sep.direction("out") == (0, -1)
    assert sep.direction("drain") == (0, 1)


def test_separator_utube_flip_ports():
    """flip=True 镜像:in 换到东侧 / out 换到西侧,drain 不动。"""
    sep = parts.make_separator_utube(flip=True)
    xin, yin = sep.port("in")
    xout, yout = sep.port("out")
    xd, yd = sep.port("drain")
    assert (round(xin, 1), yin) == (43.8, -75.0)
    assert (round(xout, 1), yout) == (-52.2, -75.0)
    assert (xd, round(yd, 1)) == (0, 54.6)
    assert sep.direction("in") == (0, -1)
    assert sep.direction("out") == (0, -1)


def test_part_unknown_port_error_lists_available():
    hx = parts.make_heat_exchanger()
    e = _raises(KeyError, hx.port, "topp")
    assert "没有端口" in str(e) and "top" in str(e)
    n = Diagram(width=100, height=100).add(parts.globe_valve, None,
                                            loc=(50, 50))
    e = _raises(KeyError, lambda: n["top"])
    assert "截止阀" in str(e)


def test_via_bad_token_error_message():
    d = Diagram(width=200, height=200, default_step=100)
    e = _raises(ValueError, d.pipe((0, 0), (50, 50), via=["q"]).points)
    assert "via[0]" in str(e) and "方向令牌" in str(e)
    e = _raises(ValueError, d.pipe((0, 0), (50, 50), via=[("q", 10)]).points)
    assert "via[0]" in str(e)
    # 非走点类型(标量)与过长坐标元组都要给出可读提示
    e = _raises(ValueError, d.pipe((0, 0), (50, 50), via=[5]).points)
    assert "不是合法走点" in str(e)
    e = _raises(ValueError, d.pipe((0, 0), (50, 50), via=[(1, 2, 3)]).points)
    assert "不是合法走点" in str(e)


def test_via_valid_tokens_still_route():
    d = Diagram(width=400, height=300, default_step=100)
    assert d.pipe((0, 0), (50, 50), via=["e"]).points()[1] == (100.0, 0.0)
    assert d.pipe((0, 0), (50, 50), via=[("n", 30)]).points()[1] == (0.0, 30.0)
    # 坐标走点经正交化后作为拐点出现在折线中
    pts = d.pipe((0, 0), (50, 50), via=[(10.5, 20.5)]).points()
    assert (10.5, 20.5) in pts and pts[0] == (0.0, 0.0) \
        and pts[-1] == (50.0, 50.0)


def test_resolve_at_tokens_and_error():
    assert _resolve_at("start") == 0.0
    assert _resolve_at("MID") == 0.5
    assert _resolve_at("End") == 1.0
    assert _resolve_at(0.3) == 0.3
    e = _raises(ValueError, _resolve_at, "middle")
    assert "start" in str(e) and "mid" in str(e)
    assert _raises(ValueError, _resolve_at, -0.1)
    assert _raises(ValueError, _resolve_at, 1.1)


def test_degenerate_diagram_and_pipe():
    # 零尺寸画布:允许构造并出图(不抛异常)
    d = Diagram(width=0, height=0)
    d.pipe((0, 0), (0, 0))
    d.render()
    # 同点/空 via 管线:退化为单点折线,不炸
    d2 = Diagram(width=100, height=100)
    assert d2.pipe((10, 10), (10, 10)).points() == [(10.0, 10.0), (10.0, 10.0)]
    assert d2.pipe((0, 0), (50, 50)).points() == [(0.0, 0.0), (0.0, 50.0),
                                                   (50.0, 50.0)]


def test_diagram_rejects_invalid_dimensions():
    """画布尺寸和默认步长必须是有限的合法数值。"""
    for kw in ({"width": -1}, {"height": -1}, {"default_step": 0},
               {"width": "wide"}):
        assert _raises(ValueError, Diagram, **kw)


def test_save_writes_readable_image(tmp_path=None):
    import tempfile
    tmp = tmp_path if tmp_path is not None else tempfile.mkdtemp()
    d = Diagram(width=200, height=120)
    d.add(parts.compressor, "压缩机", loc=(100, 60))
    d.pipe((0, 0), (60, 60))

    png = d.save(os.path.join(tmp, "out.png"))
    head = open(png, "rb").read(8)
    assert head == b"\x89PNG\r\n\x1a\n"
    assert os.path.getsize(png) > 1000

    svg = d.save(os.path.join(tmp, "out.svg"))
    with open(svg, "rb") as f:
        body = f.read()
    assert b"<svg" in body and b"</svg>" in body

    # 读回 PNG 校验:画布尺寸正确且画面非纯白
    import matplotlib.pyplot as plt
    img = plt.imread(png)
    assert img.shape[0] >= 100 and img.shape[1] >= 180
    assert (img[..., :3] < 0.99).any(), "渲染结果应包含非白像素"


def test_render_every_part_and_hvac_symbol(tmp_path=None):
    """烟雾测试:部件库与 HVAC 符号全部上屏渲染,防止画图代码静默腐坏。

    不做像素级回归——中文字体跨平台差异会让参考图比对脆到不可用,
    这里改为校验"画得出来 + 落盘非空"。
    """
    import tempfile

    from rrplot import hvac
    from rrplot.parts import Part
    tmp = tmp_path if tmp_path is not None else tempfile.mkdtemp()

    # hvac 工厂函数自动发现:排除导入进来的 matplotlib 类/原语(模块名不同),
    # 新增符号无需再手工登记;数量下限兜底防漏。
    hvac_factories = [name for name, obj in vars(hvac).items()
                      if callable(obj) and not name.startswith("_")
                      and getattr(obj, "__module__", None) == hvac.__name__]
    assert len(hvac_factories) >= 17, f"hvac 工厂过少:{hvac_factories}"
    items = [(k, v) for k, v in vars(parts).items() if isinstance(v, Part)
             and not k.startswith("_")]
    items += [(name, getattr(hvac, name)()) for name in hvac_factories]

    d = Diagram(width=1400, height=900)
    i = 0
    for name, obj in items:
        if isinstance(obj, Part) and not str(name).startswith("_"):
            d.add(obj, None, loc=(110 + (i % 7) * 195, 90 + (i // 7) * 150))
            i += 1
    assert i >= 30, f"可渲染图元过少:{i}"
    d.render()
    png = d.save(os.path.join(tmp, "all_parts.png"))
    assert os.path.getsize(png) > 10_000
    import matplotlib.pyplot as plt
    plt.close(d.fig)


def test_render_every_svg_symbol(tmp_path=None):
    """references/hvacsvg/symbols 下每个 SVG 都能加载并渲染。"""
    import glob
    import tempfile

    from rrplot.parts import Part
    tmp = tmp_path if tmp_path is not None else tempfile.mkdtemp()
    sym_dir = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "references", "hvacsvg", "symbols")
    files = sorted(glob.glob(os.path.join(sym_dir, "*.svg")))
    assert files, "未找到 SVG 符号源文件"

    d = Diagram(width=1400, height=900)
    loaded = []
    for i, f in enumerate(files):
        loaded.append(load_svg_part(f))
    for i, p in enumerate(loaded):
        assert isinstance(p, Part)
        d.add(p, None, loc=(110 + (i % 7) * 195, 90 + (i // 7) * 150))
    png = d.save(os.path.join(tmp, "all_svg.png"))
    assert os.path.getsize(png) > 10_000
    import matplotlib.pyplot as plt
    plt.close(d.fig)


def test_render_all_compressor_styles(tmp_path=None):
    """压缩机全部 style 都能渲染(防止纯几何画法静默腐坏)。"""
    import tempfile
    tmp = tmp_path if tmp_path is not None else tempfile.mkdtemp()
    d = Diagram(width=len(parts.COMPRESSOR_STYLES) * 200 + 40, height=260)
    for i, style in enumerate(parts.COMPRESSOR_STYLES):
        d.add(parts.make_compressor(70, style=style), f"s{i}",
              loc=(140 + i * 200, 130))
    png = d.save(os.path.join(tmp, "compressors.png"))
    assert os.path.getsize(png) > 5_000
    import matplotlib.pyplot as plt
    plt.close(d.fig)


def test_render_all_heat_exchanger_shapes(tmp_path=None):
    """换热器全部 shape 都能渲染。"""
    import tempfile
    tmp = tmp_path if tmp_path is not None else tempfile.mkdtemp()
    d = Diagram(width=len(parts.HEX_SHAPES) * 200 + 40, height=260)
    for i, shape in enumerate(parts.HEX_SHAPES):
        d.add(parts.make_heat_exchanger(140, 90, shape=shape), f"h{i}",
              loc=(140 + i * 200, 130))
    png = d.save(os.path.join(tmp, "hex.png"))
    assert os.path.getsize(png) > 5_000
    import matplotlib.pyplot as plt
    plt.close(d.fig)


def test_render_all_labels_on_and_off(tmp_path=None):
    """每个部件在 label 有/无两种情况下都能渲染(覆盖 if label 分支)。"""
    import tempfile

    from rrplot.parts import Part
    tmp = tmp_path if tmp_path is not None else tempfile.mkdtemp()
    d = Diagram(width=1400, height=900)
    i = 0
    for k, v in vars(parts).items():
        if isinstance(v, Part) and not k.startswith("_"):
            d.add(v, "X", loc=(110 + (i % 7) * 195, 90 + (i // 7) * 150))
            i += 1
    d.render()
    import matplotlib.pyplot as plt
    plt.close(d.fig)

    d2 = Diagram(width=1400, height=900)
    j = 0
    for k, v in vars(parts).items():
        if isinstance(v, Part) and not k.startswith("_"):
            d2.add(v, None, loc=(110 + (j % 7) * 195, 90 + (j // 7) * 150))
            j += 1
    png = d2.save(os.path.join(tmp, "nolabel.png"))
    assert os.path.getsize(png) > 10_000
    plt.close(d2.fig)


def test_svg_part_bridge_and_label_dy():
    """bridge 引管与 label_dy 不改端口偏移,且能渲染。"""
    sym = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "references", "hvacsvg", "symbols", "02_水泵.svg")
    p = load_svg_part(sym, bridge=20, label_dy=0)
    # bridge 只是画引管,不该影响端口定义
    assert p.port("in") == (-80.0, 0.0)
    assert p.port("out") == (80.0, 0.0)

    d = Diagram(width=300, height=200)
    d.add(p, "水泵", loc=(150, 100))
    d.render()
    import matplotlib.pyplot as plt
    plt.close(d.fig)


def test_render():
    """render() 返回 fig,并把部件与管线都画上。"""
    d = Diagram(width=200, height=150)
    n = d.add(parts.compressor, "压缩机", loc=(100, 75))
    d.pipe(n["discharge"], n["suction"])
    fig = d.render()
    assert fig is d.fig


def test_diagram_close_and_context_manager():
    """close() 注销 figure;上下文管理器退出时自动关闭。"""
    d = Diagram(width=120, height=90)
    num = d.fig.number
    assert num in plt.get_fignums()
    d.close()
    assert num not in plt.get_fignums()
    with Diagram(width=120, height=90) as d2:
        assert d2.fig.number in plt.get_fignums()
    assert d2.fig.number not in plt.get_fignums()


def test_clear_render_rebuilds_after_node_mutation():
    """修改节点位置后可清空旧图层并重新绘制。"""
    d = Diagram(width=240, height=140)
    node = d.add(parts.filter, None, loc=(60, 70))
    d.render()
    first = d.ax.patches[0].get_xy()
    node.loc = (180, 70)
    d.clear_render().render()
    second = d.ax.patches[0].get_xy()
    assert first != second
    assert second[0] > first[0]
    plt.close(d.fig)


def test_clear_render_recomputes_modified_pipe_routes():
    with Diagram(width=240, height=160) as diagram:
        pipe = diagram.pipe((0, 0), (200, 100), via=[(50, 50)], head=False)
        diagram.render()
        original = list(pipe.points())
        pipe.via = [(100, 80)]
        diagram.clear_render().render()
        assert pipe.points() == [(0, 0), (0, 80), (100, 80), (200, 80), (200, 100)]
        assert pipe.points() != original
        assert list(zip(*diagram.ax.lines[0].get_data())) == pipe.points()
        line_count = len(diagram.ax.lines)
        diagram.render()
        diagram.render()
        assert len(diagram.ax.lines) == line_count


def test_sensor_and_text_helpers():
    """Diagram.sensor()/text() 都能落笔,不报错。"""
    d = Diagram(width=200, height=150)
    d.sensor(40, 40, "T_1")
    d.text(160, 40, "回水", ha="left", boxed=True)
    d.render()
    import matplotlib.pyplot as plt
    plt.close(d.fig)


def test_state_instance_and_full_options():
    """State 实例可直接传;dict 形式支持 side/kind/size 全参数。"""
    d = Diagram(width=200, height=150)
    from rrplot.core import State
    st = State("1", 0.5)
    d.pipe((0, 0), (100, 0), states=st)
    d.pipe((0, 10), (100, 10),
           states=[{"text": "$T_1$", "at": 0.5, "side": 1, "size": 18}])
    d.pipe((0, 20), (100, 20),
           states=[{"text": "2", "at": 0.5, "side": -1, "size": 12}])
    # 强制 kind,绕过 _is_sensor 自动判定
    d.pipe((0, 30), (100, 30),
           states=[{"text": "9", "at": 0.5, "kind": "sensor"}])
    d.render()
    import matplotlib.pyplot as plt
    plt.close(d.fig)


def test_fit_end_free_port_zero_dir():
    """端口法向为零(自由端)时 _fit_end 不做吸附。"""
    pts = [(100.0, 50.0), (108.0, 0.0), (170.0, 0.0)]
    free = Port((100.0, 50.0), (0.0, 0.0), None)
    assert _fit_end(pts, True, free) is None
    assert pts[1] == (108.0, 0.0)   # 坐标未被改动


def test_fit_end_tangent_aligned_normal_offset():
    """邻段与端口同轴、法向错位在容差内:直接吸附到端口法向。"""
    pts = [(100.0, 50.0), (105.0, 0.0)]
    assert _fit_end(pts, True, _port((100.0, 50.0), "e")) is None
    assert pts[1] == (100.0, 0.0)


def test_use_font_prints(capsys=None):
    """use_font() 打印当前生效字体,且返回字体名。"""
    from rrplot.style import FONT, use_font
    out = use_font()
    assert out == FONT
    if capsys is not None:                 # pytest 下校验打印内容
        assert "使用字体" in capsys.readouterr().out


def test_style_context_restores_matplotlib_rcparams():
    """样式上下文退出后恢复调用方的 Matplotlib 配置。"""
    import matplotlib

    from rrplot.style import context

    before = matplotlib.rcParams["mathtext.fontset"]
    with context(**{"mathtext.fontset": "dejavusans"}):
        assert matplotlib.rcParams["mathtext.fontset"] == "dejavusans"
    assert matplotlib.rcParams["mathtext.fontset"] == before


def test_cycleplot_compatibility_alias():
    """旧包名仍可导入,且与 rrplot 使用同一版本。"""
    import importlib
    import warnings

    importlib.invalidate_caches()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        import cycleplot
        importlib.reload(cycleplot)
    import cycleplot.scene

    import rrplot

    assert cycleplot.__version__ == rrplot.__version__
    assert cycleplot.Diagram is Diagram
    assert cycleplot.scene.SCHEMA_VERSION == 1
    assert any(issubclass(w.category, DeprecationWarning) for w in caught)


def test_part_model_is_shared_without_loading_registry():
    """SVG/HVAC 与部件注册表共享同一个 Part 数据模型。"""
    from rrplot.part import Part

    assert parts.Part is Part


def test_repr_svg_and_render_idempotent():
    """_repr_svg_ 输出 SVG;render() 重复调用不重复叠加图元。"""
    d = Diagram(width=150, height=120)
    d.add(parts.compressor, "压缩机", loc=(75, 60))
    d.render()
    n = len(d.ax.patches)
    d.render()
    assert len(d.ax.patches) == n
    svg = d._repr_svg_()
    assert "<svg" in svg and "</svg>" in svg
    d._repr_svg_()                     # 富显示可反复触发,不叠加
    assert len(d.ax.patches) == n
    plt.close(d.fig)


def test_debug_overlay():
    """debug() 叠加端口点/法向箭头/拐点标记,只读不改走线坐标。"""
    d = Diagram(width=280, height=160)
    a = d.add(parts.make_heat_exchanger(96, 48), "蒸发器", loc=(70, 90))
    b = d.add(parts.compressor, "压缩机", loc=(210, 90))
    pipe = d.pipe(a["top"], b["suction"], via=[("e", 140)])
    pts0 = list(pipe.points())
    d.render()
    n = len(d.ax.patches)
    d.debug(names=True)
    assert len(d.ax.patches) > n
    assert pipe.points() == pts0
    plt.close(d.fig)


def test_save_multiple_formats(tmp_path=None):
    """save() 一次传多个路径输出多格式;单路径仍返回路径字符串。"""
    import tempfile
    tmp = tmp_path if tmp_path is not None else tempfile.mkdtemp()
    d = Diagram(width=200, height=140)
    d.add(parts.filter, "过滤器", loc=(100, 70))
    png, svg, pdf = d.save(os.path.join(tmp, "m.png"),
                           os.path.join(tmp, "m.svg"),
                           os.path.join(tmp, "m.pdf"))
    assert os.path.getsize(png) > 1000
    with open(svg, "rb") as f:
        assert b"<svg" in f.read()
    assert os.path.getsize(pdf) > 1000
    assert d.save(os.path.join(tmp, "s.png")) == os.path.join(tmp, "s.png")
    plt.close(d.fig)


def test_polyline_span_end_preserves_last_segment_direction():
    """frac=1.0 即使浮点累加略小于总长,也应停在末段并保留末段方向。"""
    from rrplot.core import _polyline_span

    # 多段非精确二进制小数,验证末段朝左/向上时不误落回 (1.0, 0.0)
    pts = [(0.0, 0.0), (0.0, -0.1), (0.0, -0.2), (0.0, -0.3), (-0.3, -0.3)]
    pt, direction, s0, s1, total = _polyline_span(pts, 1.0)
    assert pt == (-0.3, -0.3)
    assert direction == (-1.0, 0.0)
    assert s1 > s0 and abs(s1 - total) < 1e-12
    # 超过 1.0 的浮点误差仍应被钳在末段终点而非掉出循环
    pt2, dir2, s0_2, s1_2, _ = _polyline_span(pts, 1.0 + 1e-15)
    assert pt2 == (-0.3, -0.3)
    assert dir2 == (-1.0, 0.0)
    assert s1_2 > s0_2


def test_refresh_fonts_updates_shared_font_stack_in_place():
    """修改 FONT_CANDIDATES 后 refresh_fonts() 原地更新 FONT_STACK。"""
    from rrplot import _primitives, style

    before_candidates = list(style.FONT_CANDIDATES)
    before_stack = list(style.FONT_STACK)
    try:
        assert _primitives.FONT_STACK is style.FONT_STACK
        if len(before_stack) >= 2:
            second = before_stack[1]
            style.FONT_CANDIDATES.remove(second)
            style.FONT_CANDIDATES.insert(0, second)
            chosen = style.refresh_fonts()
            assert chosen == second
            assert style.FONT == second
            assert _primitives.FONT_STACK[0] == second
        else:
            assert style.refresh_fonts() == style.FONT
        # 验证 register_font() 能注册字体文件并置顶候选栈
        sample_ttf = style.fm.fontManager.ttflist[0].fname
        registered = style.register_font(sample_ttf)
        assert registered == style.FONT == style.FONT_CANDIDATES[0]
        assert _primitives.FONT_STACK[0] == registered
    finally:
        style.FONT_CANDIDATES[:] = before_candidates
        style.refresh_fonts()
        assert style.FONT_STACK == before_stack


def test_vessel_filter_validation_and_svg_comma_viewbox(tmp_path=None):
    """make_vessel / make_filter 边界校验,以及逗号分隔且非零起点的 viewBox。"""
    import tempfile

    _raises(ValueError, parts.make_vessel, w=100, h=50)
    _raises(ValueError, parts.make_filter, n=0)
    _raises(ValueError, parts.make_filter, n=True)

    tmp = tmp_path if tmp_path is not None else tempfile.mkdtemp()
    svg_path = os.path.join(tmp, "comma_vb.svg")
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="10,20,100,60" '
            'data-connection-points=\'[{"id":"in","x":10,"y":50},'
            '{"id":"out","x":110,"y":50}]\'>'
            '<rect x="20" y="30" width="80" height="40" fill="none" stroke="black"/>'
            "</svg>"
        )
    part = load_svg_part(svg_path, bridge=10)
    assert part.port("in") == (-50.0, 0.0)
    assert part.port("out") == (50.0, 0.0)
    with Diagram(width=200, height=120) as d:
        d.add(part, "测试", loc=(100, 60))
        d.render()

    bad_vb = os.path.join(tmp, "bad_vb.svg")
    with open(bad_vb, "w", encoding="utf-8") as f:
        f.write('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100"/>')
    _raises(ValueError, load_svg_part, bad_vb)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
