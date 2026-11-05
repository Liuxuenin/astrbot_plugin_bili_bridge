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


def test_bvs_in_order():
    """推送私信里三条视频的顺序，要按出现顺序取出来（去重、不乱序）。

    这串顺序就是主人在 QQ 上看到的 1./2./3.；「第一个视频」必须以它为准，
    不能用记忆块那份重排过的清单（2026-11 实测答错过视频）。
    """

    text = (
        "今天挑了三条：\n"
        "1. 甲视频 https://www.bilibili.com/video/BV1aaaaaaaaa\n"
        "2. 乙视频 https://www.bilibili.com/video/BV1bbbbbbbbb\n"
        "3. 丙视频 https://www.bilibili.com/video/BV1ccccccccc\n"
        "（乙视频再贴一次也不该重复：BV1bbbbbbbbb）"
    )
    assert mod.bvs_in_order(text) == [
        "BV1aaaaaaaaa",
        "BV1bbbbbbbbb",
        "BV1ccccccccc",
    ], mod.bvs_in_order(text)
    assert mod.bvs_in_order("没有 BV 的句子") == []
    assert mod.bvs_in_order("") == []
    print("ok  推送顺序解析")


def test_markdown_bullet_rows():
    """digest 里带列表符号（- / * / 1.）的行也要能解析。

    2026-11 实测踩过：生成端写的是 `- 2026-11-02 · BV…`，旧正则只认行首日期，
    整份文件一行都匹配不上，同步静默跳过、日志里什么都看不到。
    """

    base = row("2026-11-02", "BV1bGHG6uERH", "大肥鱼机器人狂吃token", "挑了：还行")
    for line in (f"- {base}", f"* {base}", f"  - {base}", f"1. {base}", base):
        cleaned = mod.normalize_row(line)
        assert cleaned == base, (line, cleaned)
        assert mod.DIGEST_LINE_RE.match(cleaned), line
        assert mod.bv_of(cleaned) == "BV1bGHG6uERH", line
        assert mod.title_of(cleaned, 40).startswith("大肥鱼机器人"), line
    print("ok  列表符号容错")


def test_read_digest_accepts_markdown_list():
    with tempfile.TemporaryDirectory() as tmp:
        digest_dir = Path(tmp)
        lines = [
            row("2026-11-02", f"BV00{i}000000", f"视频{i}", "挑了：不错")
            for i in range(3)
        ]
        (digest_dir / "2026-11.md").write_text(
            "# 2026-11 挑片记录\n\n" + "\n".join(f"- {x}" for x in lines) + "\n",
            encoding="utf-8",
        )
        got = mod.read_digest(str(digest_dir), "跳过", 2, 4)
        assert got is not None, "带列表符号的 digest 必须能读出来"
        text, source, bvs, rows = got
        assert len(bvs) == 3, bvs
        assert source == "digest:2026-11-02", source  # 不再带 "- " 前缀
        assert "视频2" in text
    print("ok  带列表符号的 digest 能同步")


def test_scan_digest_dir_counts():
    with tempfile.TemporaryDirectory() as tmp:
        digest_dir = Path(tmp)
        good = row("2026-11-02", "BV1bGHG6uERH", "好行", "挑了：行")
        (digest_dir / "2026-11.md").write_text(
            f"- {good}\n这行没有日期\n\n## 小标题\n", encoding="utf-8"
        )
        scan = mod.scan_digest_dir(str(digest_dir))
        assert scan["exists"] and scan["file"] == "2026-11.md", scan
        assert scan["matched"] == 1, scan
        assert scan["rejected"] == 1, scan
        assert scan["sample_rejected"].startswith("这行没有日期"), scan
    missing = mod.scan_digest_dir(
        str(Path(tempfile.gettempdir()) / "no-such-digest-dir")
    )
    assert missing["exists"] is False, missing
    print("ok  体检扫描计数")


def test_fill_to_five_from_earlier_days():
    """新一轮不够数时，清单要凑满 block_picked + block_skipped（默认 5）条。

    2026-11 的实际诉求：今天只推了 2 条，问「今天看了什么」也该是 5 条——
    2 条今天的 + 从更早记录里补 3 条，而不是只报 2 条。
    """

    with tempfile.TemporaryDirectory() as tmp:
        digest_dir = Path(tmp)
        older = [
            row("2026-11-01", f"BVy{i}aaaaaaa", f"昨天{i}", "跳过：一般")
            for i in range(4)
        ]
        today = [
            row("2026-11-02", f"BVt{i}bbbbbbb", f"今天{i}", "挑了：行") for i in range(2)
        ]
        (digest_dir / "2026-11.md").write_text(
            "\n".join(older + today) + "\n", encoding="utf-8"
        )
        got = mod.read_digest(str(digest_dir), "跳过", 2, 3)
        assert got is not None
        text, source, bvs, rows = got
        assert len(bvs) == 2, bvs  # 今天确实只有 2 条
        listed = [ln for ln in text.splitlines() if ln.startswith("- ")]
        assert len(listed) == 5, listed  # 记忆块要凑满 5 条
        assert source == "digest:2026-11-02", source

        # 全量行：按日期从新到旧
        all_rows = mod.all_digest_rows(str(digest_dir))
        assert all_rows[0].startswith("2026-11-02"), all_rows[0]
        assert len(all_rows) == 6, len(all_rows)
    print("ok  凑满 5 条（跨天补）")


def test_parse_push_items_variable_count():
    """推送条数不固定：1 条、2 条、3 条都要按顺序解析出来，标题也要带上。

    2026-11 的实际反馈：上游有时只推 1 条、有时 2 条。以前只按「三条」的假设写，
    条数一变，清单第一项和「第一个」就都对不上。
    """

    three = (
        "今天挑了三条：\n"
        "1. 甲视频标题\nhttps://www.bilibili.com/video/BV1aaaaaaaaa\n"
        "2. 乙视频标题\nhttps://www.bilibili.com/video/BV1bbbbbbbbb\n"
        "3. 丙视频标题\nhttps://www.bilibili.com/video/BV1ccccccccc\n"
    )
    items = mod.parse_push_items(three)
    assert [i["bv"] for i in items] == [
        "BV1aaaaaaaaa",
        "BV1bbbbbbbbb",
        "BV1ccccccccc",
    ], items
    assert items[0]["title"] == "甲视频标题", items

    two = "今天两条：\n- 丁视频 https://www.bilibili.com/video/BV1ddddddddd\n- 戊视频 https://www.bilibili.com/video/BV1eeeeeeeee\n"
    items2 = mod.parse_push_items(two)
    assert [i["bv"] for i in items2] == ["BV1ddddddddd", "BV1eeeeeeeee"], items2

    one = "今天只有一条，别的都不太行：\n猫片 https://www.bilibili.com/video/BV1fffffffff\n"
    items1 = mod.parse_push_items(one)
    assert len(items1) == 1 and items1[0]["bv"] == "BV1fffffffff", items1
    assert "猫片" in items1[0]["title"], items1
    print("ok  推送条数不固定（1/2/3 条）")


def test_scroll_phrase():
    """「刷视频」口令：该接的接住，问内容的不许抢。"""

    hits = [
        "刷视频",
        "刷B站",
        "刷b站",
        "看视频",
        "看一下视频",
        "帮我刷一下B站",
        "快去刷视频吧",
        "去刷刷B站",
        "刷一轮",
    ]
    hits += [
        "请去刷一轮视频",      # 2026-11-05 真机漏掉的那句（前面挂个「请」）
        "请帮我刷一轮视频",
        "老大去刷视频",
    ]
    misses = [
        "今天看了什么视频",
        "B站今天刷到什么",
        "这个视频讲什么",
        "看视频吗",
        "刷B站的评论",
        "在吗",
        "泡泡你好",
        "刷视频 帮我看看有没有讲AI的",  # 太长 + 带疑问 ⇒ 交给模型
        "我不想看视频",
        "不用刷了",
        "算了不刷了",
    ]
    for text in hits:
        assert mod.is_scroll_request(text), text
    for text in misses:
        assert not mod.is_scroll_request(text), text
    assert mod.is_scroll_request("去溜溜", ["去溜溜"]), "额外触发词要认"
    print("ok  「刷视频」口令识别")


def test_parse_report_items():
    """日报里 `### BV…` 的几种写法都要能拆出来（带不带 `- ` 前缀都认）。"""

    text = (
        "# 刷B站日报 2026-11-05\n\n## 手动触发（追加）\n\n"
        "### BV1KiJk67EQ9\n"
        "- 标题：我造了一块会飞的滑板...\n"
        "- UP：神奇阿宇Ayu ｜ 链接：https://www.bilibili.com/video/BV1KiJk67EQ9 ｜ 播放：832.9 万\n"
        "- **档位**：值得看\n"
        "- 为什么值得：真造了一台载人飞行滑板。\n"
        "- 一句话：这条的信息量是「照着做一遍」级别的。\n\n"
        "### BV1onxb6rEeE\n"
        "标题：12个大模型扮演君主\n"
        "**档位**：可以看\n"
        "一句话：当故事看也值。\n"
    )
    items = mod.parse_report_items(text)
    assert [i["bv"] for i in items] == ["BV1KiJk67EQ9", "BV1onxb6rEeE"], items
    assert items[0]["title"].startswith("我造了一块"), items[0]
    assert items[0]["tier"] == "值得看", items[0]
    assert items[0]["link"] == "https://www.bilibili.com/video/BV1KiJk67EQ9", items[0]
    assert items[1]["title"].startswith("12个大模型"), items[1]
    assert items[1]["link"] == "https://www.bilibili.com/video/BV1onxb6rEeE", items[1]
    assert mod.parse_report_items("") == []
    print("ok  日报解析")


def test_parse_digest_items():
    """归档行（带档位 / 不带档位 / 跳过）都要能拆出来。"""

    text = (
        "- 2026-11-05 · BV1Rbxg6WER5 · 一个有自主意识的插件 · 玛露Marrow · "
        "人格卡+记忆卡三端共用 · 值得看 · https://www.bilibili.com/video/BV1Rbxg6WER5\n"
        "- 2026-11-05 · BV15sxS68EFq · 不看电视不接电话的中国人 · 汤山老王 · "
        "跳过（22分钟口播、无字幕） · https://www.bilibili.com/video/BV15sxS68EFq\n"
    )
    items = mod.parse_digest_items(text)
    assert len(items) == 2, items
    assert items[0]["bv"] == "BV1Rbxg6WER5"
    assert items[0]["tier"] == "值得看", items[0]
    assert "人格卡" in items[0]["note"], items[0]
    assert "跳过" in items[1]["note"], items[1]
    assert items[1]["link"] == "https://www.bilibili.com/video/BV15sxS68EFq", items[1]
    print("ok  归档行解析")


def test_mint_dsh_cookie():
    """签出来的 cookie 要能被人用同样的密钥验回来（格式：v1.<body>.<sig>）。"""

    import base64
    import hashlib
    import hmac
    import json

    secret_b64 = base64.urlsafe_b64encode(b"0123456789abcdef0123456789abcdef").decode()
    name, value = mod.mint_dsh_cookie("127.0.0.1:63825", secret_b64)
    assert name.startswith("dsh-auth-"), name
    expect = "dsh-auth-" + base64.urlsafe_b64encode(
        hashlib.sha256(b"127.0.0.1:63825").digest()
    ).decode().rstrip("=")
    assert name == expect, (name, expect)

    version, body, sig = value.split(".")
    assert version == "v1"
    payload = json.loads(
        base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)).decode("utf-8")
    )
    assert payload["authority"] == "127.0.0.1:63825", payload
    assert payload["expiresAt"] > payload["issuedAt"], payload
    mine = base64.urlsafe_b64encode(
        hmac.new(
            base64.urlsafe_b64decode(secret_b64 + "=" * (-len(secret_b64) % 4)),
            body.encode("ascii"),
            hashlib.sha256,
        ).digest()
    ).decode().rstrip("=")
    assert sig == mine, "签名对不上"
    print("ok  DSH cookie 签名")


if __name__ == "__main__":
    test_row_parsing()
    test_select_picks_latest_and_fills()
    test_select_is_deterministic()
    test_read_digest_delta_and_seen()
    test_markdown_bullet_rows()
    test_bvs_in_order()
    test_read_digest_accepts_markdown_list()
    test_scan_digest_dir_counts()
    test_fill_to_five_from_earlier_days()
    test_parse_push_items_variable_count()
    test_chunk_text()
    test_ask_regex()
    test_scroll_phrase()
    test_parse_report_items()
    test_parse_digest_items()
    test_mint_dsh_cookie()
    print("\n全部通过")
