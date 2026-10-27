"""回归测试：DSML 无类型上下文下，会改变文本形式的纯数字字符串应保留原字符串。

覆盖 backend.agents.base._parse_dsml_calls 的数值强转兜底：
- '113.50' 不应被静默转成 float 113.5（丢失尾随零）；
- '007' 不应被静默转成 int 7（丢失前导零）；
- 无损形式的数值（'113.5'、'5'）仍按既有行为转换（与既有受保护测试一致）。
"""
import json

from backend.agents.base import _parse_dsml_calls


def _content(**params: str) -> str:
    body = "".join(
        f'<｜｜DSML｜｜parameter name="{k}">{v}</｜｜DSML｜｜parameter>'
        for k, v in params.items()
    )
    return (
        "<｜｜DSML｜｜tool_calls>"
        '<｜｜DSML｜｜invoke name="xhs_search">'
        + body
        + "</｜｜DSML｜｜invoke>"
        "</｜｜DSML｜｜tool_calls>"
    )


def _parse_args(content: str) -> dict:
    calls = _parse_dsml_calls(content)
    assert calls, "应解析出至少一个 DSML 调用"
    return json.loads(calls[0]["arguments"])


def test_trailing_zero_numeric_string_kept_as_string():
    args = _parse_args(_content(keyword="113.50"))
    assert args["keyword"] == "113.50"
    assert isinstance(args["keyword"], str)
    assert not isinstance(args["keyword"], (int, float))


def test_leading_zero_numeric_string_kept_as_string():
    args = _parse_args(_content(tag="007"))
    assert args["tag"] == "007"
    assert isinstance(args["tag"], str)


def test_scientific_notation_kept_as_string():
    args = _parse_args(_content(scale="1e5"))
    assert args["scale"] == "1e5"
    assert isinstance(args["scale"], str)


def test_lossless_numbers_still_converted():
    args = _parse_args(_content(lng="113.5", limit="5"))
    assert args["lng"] == 113.5
    assert isinstance(args["lng"], float)
    assert args["limit"] == 5
    assert isinstance(args["limit"], int)


def test_mixed_params_keep_forms():
    args = _parse_args(_content(keyword="113.50", label="2024", count="12"))
    assert args["keyword"] == "113.50"
    assert isinstance(args["keyword"], str)
    assert args["label"] == 2024
    assert isinstance(args["label"], int)
    assert args["count"] == 12
