"""核心解析函数的单测：纯函数、零外部依赖，本地 + CI 都能跑。"""
from __future__ import annotations

import json

from backend.agents.base import _parse_dsml_calls
from backend.mcp.amap import (
    _normalize_geo,
    _normalize_poi_list,
    _normalize_regeo,
)
from backend.mcp.train12306 import _normalize_tickets
from backend.mcp.xhs import _normalize_feeds
from backend.orchestrator import _extract_decision


# ---------- orchestrator: manager JSON 兜底解析 ----------

def test_extract_decision_plain_json():
    raw = '{"next_agent": "planning_agent", "subtask": "成都两日游", "thought": "a", "final_answer": ""}'
    obj = _extract_decision(raw)
    assert obj is not None
    assert obj["next_agent"] == "planning_agent"


def test_extract_decision_with_markdown_fence():
    raw = '```json\n{"next_agent": "final", "final_answer": "你好"}\n```'
    obj = _extract_decision(raw)
    assert obj is not None
    assert obj["next_agent"] == "final"
    assert obj["final_answer"] == "你好"


def test_extract_decision_double_wrapped():
    inner = '{"next_agent": "navigation_agent", "subtask": "找地铁", "thought": "x", "final_answer": ""}'
    raw = f'前导废话 {inner} 后续解释'
    obj = _extract_decision(raw)
    assert obj is not None
    assert obj["next_agent"] == "navigation_agent"


def test_extract_decision_returns_none_on_garbage():
    assert _extract_decision("") is None
    assert _extract_decision("纯自然语言，没有结构") is None


# ---------- DeepSeek DSML tool_calls 兜底 ----------

def test_parse_dsml_calls_basic():
    raw = (
        '<｜｜DSML｜｜tool_calls>\n'
        '  <｜｜DSML｜｜invoke name="amap_around_search">\n'
        '    <｜｜DSML｜｜parameter name="lng">113.5</｜｜DSML｜｜parameter>\n'
        '    <｜｜DSML｜｜parameter name="lat">23.1</｜｜DSML｜｜parameter>\n'
        '    <｜｜DSML｜｜parameter name="keyword">地铁站</｜｜DSML｜｜parameter>\n'
        '    <｜｜DSML｜｜parameter name="radius">1500</｜｜DSML｜｜parameter>\n'
        '  </｜｜DSML｜｜invoke>\n'
        '</｜｜DSML｜｜tool_calls>'
    )
    calls = _parse_dsml_calls(raw)
    assert len(calls) == 1
    assert calls[0]["name"] == "amap_around_search"
    args = json.loads(calls[0]["arguments"])
    assert args == {"lng": 113.5, "lat": 23.1, "keyword": "地铁站", "radius": 1500}


def test_parse_dsml_calls_no_dsml_returns_empty():
    assert _parse_dsml_calls("") == []
    assert _parse_dsml_calls("普通自然语言回复") == []


# ---------- 高德归一化 ----------

def test_normalize_regeo_extracts_township_and_street():
    raw = {
        "addressComponent": {
            "city": "广州市",
            "district": "黄埔区",
            "township": "鱼珠街道",
            "neighborhood": {"name": "黄埔花园"},
            "streetNumber": {"street": "黄埔东路", "number": "888号"},
        },
        "formatted_address": "广东省广州市黄埔区鱼珠街道黄埔东路888号",
    }
    info = _normalize_regeo(raw, 113.51, 23.10)
    assert info["city"] == "广州市"
    assert info["district"] == "黄埔区"
    assert info["township"] == "鱼珠街道"
    assert info["street"] == "黄埔东路"
    assert "黄埔" in info["address"]


def test_normalize_geo_handles_results_key():
    raw = {
        "results": [
            {"location": "113.27,23.13", "formatted_address": "广州塔"}
        ]
    }
    geo = _normalize_geo(raw)
    assert geo == {"location": "113.27,23.13", "formatted_address": "广州塔"}


def test_normalize_poi_list_unwraps_dict_with_pois_key():
    raw = {
        "pois": [
            {"name": "鱼珠地铁站", "address": "黄埔东路", "location": "113.51,23.10"},
            {"name": "黄埔站", "address": "鱼珠路", "location": "113.50,23.11"},
        ]
    }
    pois = _normalize_poi_list(raw)
    assert len(pois) == 2
    assert pois[0]["name"] == "鱼珠地铁站"


# ---------- 小红书 feeds ----------

def test_normalize_feeds_real_shape():
    raw = {
        "feeds": [
            {
                "id": "abc123",
                "xsecToken": "tok",
                "noteCard": {
                    "displayTitle": "成都 3 天保姆攻略",
                    "user": {"nickname": "小薯条"},
                    "interactInfo": {"likedCount": "12345"},
                    "cover": {"urlDefault": "https://x/img.jpg"},
                },
            }
        ]
    }
    feeds = _normalize_feeds(raw, limit=3)
    assert len(feeds) == 1
    f = feeds[0]
    assert f["title"] == "成都 3 天保姆攻略"
    assert f["author"] == "小薯条"
    assert f["likes"] == 12345
    assert f["url"].startswith("https://www.xiaohongshu.com/explore/abc123")
    assert "tok" in f["url"]


# ---------- 12306 tickets ----------

def test_normalize_tickets_picks_seat_prices_and_builds_url():
    raw = [
        {
            "train_no": "240000G12340",
            "start_train_code": "G123",
            "start_time": "08:00",
            "arrive_time": "12:30",
            "lishi": "04:30",
            "from_station": "北京南",
            "to_station": "上海虹桥",
            "from_station_telecode": "VNP",
            "to_station_telecode": "AOH",
            "prices": [
                {"seat_name": "二等座", "price": "553.5", "num": "12"},
                {"seat_name": "一等座", "price": "933.0", "num": "5"},
                {"seat_name": "商务座", "price": "1748.0", "num": "无"},
            ],
        }
    ]
    out = _normalize_tickets(raw, "2026-05-17")
    assert len(out) == 1
    t = out[0]
    assert t["train_no"] == "G123"
    assert t["depart"] == "北京南 08:00"
    assert t["arrive"] == "上海虹桥 12:30"
    assert t["second_class"] == 553.5
    assert t["first_class"] == 933.0
    assert t["business"] == 1748.0
    assert "kyfw.12306.cn" in t["url"]
    assert "VNP" in t["url"] and "AOH" in t["url"]
    assert "2026-05-17" in t["url"]
