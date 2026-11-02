"""不依赖 pytest 的最小测试：直接 `python tests/test_basic.py`。

覆盖不涉及网络的纯逻辑：行解析、六条选取、去重与增量判断、文本切段。
"""

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ASTRBOT_ROOT = os.environ.get("ASTRBOT_ROOT", r"C:\QQBot\astrbot\AstrBot-master")
sys.path.insert(0, ASTRBOT_ROOT)

HERE = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "bili_bridge_under_test", HERE / "main.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def row(date, bv, title, tier):
    return (
        f"{date} · {bv} · {title} · 某UP · {tier} · https://www.bilibili.com/video/{bv}"
    )


def test_row_parsing():
    r = row("2026-11-02", "BV1bGHG6uERH", "大肥鱼机器人狂吃token", "挑了：还行")
    assert mod.bv_of(r) == "BV1bGHG6uERH"
    assert mod.title_of(r, 40).startswith("大肥鱼机器人")
    assert mod.title_of(r, 4) == "大肥鱼机…", mod.title_of(r, 4)
    print("ok  行解析")


def test_select_picks_latest_and_fills():
    day = [
        row("2026-11-02", f"BV00{i}000000", f"视频{i}", "跳过：无关") for i in range(10)
    ]
    day.append(row("2026-11-02", "BV9999999999", "最新挑中的", "挑了：好"))
    shown = mod.select_display_rows(
        day[-3:], day, "跳过", picked_count=2, skipped_count=4
    )
    assert len(shown) == 6, shown
    assert shown[0] == day[-1], "挑中的应该排在最前"
    assert mod.bv_of(shown[0]) == "BV9999999999"
    print("ok  六条选取与补足")


def test_select_is_deterministic():
    day = [
        row("2026-11-02", f"BV00{i}000000", f"视频{i}", "跳过：无关") for i in range(20)
    ]
    a = mod.select_display_rows(day, day, "跳过", 2, 4)
    b = mod.select_display_rows(day, day, "跳过", 2, 4)
    assert a == b, "同样输入必须抽出同样的条目（否则「第几个」会错位）"
    print("ok  抽样稳定")


def test_read_digest_delta_and_seen():
    with tempfile.TemporaryDirectory() as tmp:
        digest_dir = Path(tmp) / "digest"
        digest_dir.mkdir()
        f = digest_dir / "2026-11.md"
        rows = [
            row("2026-11-02", "BVaaaaaaaaaa", "老视频一", "跳过：无关"),
            row("2026-11-02", "BVbbbbbbbbbb", "老视频二", "跳过：无关"),
        ]
        f.write_text("### 2026-11-02\n" + "\n".join(rows) + "\n", encoding="utf-8")

        first = mod.read_digest(str(digest_dir), "跳过", 2, 4, "", set())
        assert first is not None
        assert len(first[3]) == 2, first[3]

        # 全部见过 → 没有新内容
        seen = {mod.bv_of(r) for r in rows}
        assert mod.read_digest(str(digest_dir), "跳过", 2, 4, "", seen) is None

        # 追加一条新的 → 只报新的
        new_row = row("2026-11-02", "BVcccccccccc", "新视频", "挑了：不错")
        f.write_text(
            "### 2026-11-02\n" + "\n".join(rows + [new_row]) + "\n", encoding="utf-8"
        )
        second = mod.read_digest(str(digest_dir), "跳过", 2, 4, "", seen)
        assert second is not None
        assert [mod.bv_of(r) for r in second[3]] == ["BVcccccccccc"], second[3]
        assert "新视频" in second[0]
        print("ok  增量识别（按 BV）")


def test_chunk_text():
    long_text = "\n".join(f"第{i}行内容" for i in range(200))
    chunks = mod.BiliBridgePlugin._chunk_text(long_text, limit=100)
    assert len(chunks) > 1
    assert all(len(c) <= 120 for c in chunks), [len(c) for c in chunks]
    assert "第0行" in chunks[0]
    assert "第199行" in chunks[-1]
    print("ok  长文本切段")


def test_ask_regex():
    plugin = mod.BiliBridgePlugin
    hits = ["今天刷到什么？", "b站最近看了什么", "这一轮刷了啥"]
    misses = ["大肥鱼那条讲了什么", "这个视频有多少播放量", "今天午饭吃什么"]
    for text in hits:
        assert plugin.ASK_LIST_RE.search(text), text
    for text in misses:
        assert not plugin.ASK_LIST_RE.search(text), text
    print("ok  问句识别")


if __name__ == "__main__":
    test_row_parsing()
    test_select_picks_latest_and_fills()
    test_select_is_deterministic()
    test_read_digest_delta_and_seen()
    test_chunk_text()
    test_ask_regex()
    print("\n全部通过")
