"""回归测试：DSML 参数解析不应把 'true'/'false' 强制转成布尔值。"""
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
    import json

    return json.loads(calls[0]["arguments"])


def test_true_string_not_coerced_to_bool():
    args = _parse_args(_content(keyword="true"))
    assert args["keyword"] == "true"
    assert isinstance(args["keyword"], str)


def test_false_and_mixed_case_strings_not_coerced():
    args = _parse_args(_content(flag="false", tag="True", kw="subway_true"))
    assert args["flag"] == "false"
    assert args["tag"] == "True"
    assert args["kw"] == "subway_true"
    assert not any(isinstance(v, bool) for v in args.values())


def test_numbers_still_converted():
    args = _parse_args(_content(lng="113.5", limit="5"))
    assert args["lng"] == 113.5
    assert args["limit"] == 5


def test_non_dsml_content_returns_empty():
    assert _parse_dsml_calls("普通文本") == []
    assert _parse_dsml_calls("") == []
