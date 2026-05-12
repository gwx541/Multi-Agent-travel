"""境外目的地识别 + ctrip shim 的单测：纯函数零依赖，本地 + CI 都能跑。"""
from __future__ import annotations

import warnings

from backend.utils.locale import detect_overseas


def test_detect_country():
    # 国家名直接命中
    assert detect_overseas("冰岛玩俩天") == "冰岛"
    assert detect_overseas("想去日本玩一周") == "日本"
    assert detect_overseas("十一去泰国蜜月") == "泰国"


def test_detect_city():
    # 知名境外城市命中
    assert detect_overseas("东京三天怎么玩") == "东京"
    assert detect_overseas("巴黎五日游求推荐") == "巴黎"
    assert detect_overseas("纽约 + 波士顿 7 天") == "纽约"


def test_detect_cross_border():
    # 出发地是国内、目的地境外，应识别为境外
    assert detect_overseas("广州飞东京三天") == "东京"
    assert detect_overseas("从上海出发去首尔") == "首尔"


def test_domestic_returns_none():
    # 全是国内城市，不应误命中
    assert detect_overseas("成都两日游") is None
    assert detect_overseas("广州 5 月去厦门玩") is None
    assert detect_overseas("北京-上海高铁怎么订") is None


def test_empty_input():
    assert detect_overseas("") is None
    assert detect_overseas("    ") is None


def test_ctrip_shim_re_exports_hotel():
    """模块改名 hotel 后，ctrip 仍作为 shim 工作，老引用零成本。"""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        from backend.mcp import ctrip, hotel

    assert ctrip.search_hotels is hotel.search_hotels
