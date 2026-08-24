#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
adapters.py —— 把各种来源的聊天记录，转成一份标准中间格式。

为什么需要它：
    2026 年微信导出工具几乎被扫平（见 references/get-your-data.md），任何绑死微信的方案
    都会随时失效。所以这个 skill 不绑定微信——它分析的是「你自己写下的字」，
    微信只是其中一个（目前最不友好的）来源。

    每个适配器只干一件事：读一种来源，吐出统一字段。清洗、脱敏、过滤全部交给
    extract_me.py，保证不同来源走同一条路，结论可比。

输出的标准字段（JSONL，一行一条）：
    time        字符串或 unix 时间戳
    is_sender   1 = 我说的，0 = 别人说的
    content     正文
    talker      会话对象的原始标识（后续会被脱敏）

支持的来源：
    imessage        Mac 本地 ~/Library/Messages/chat.db —— 最可靠，无需任何第三方工具
    chatlog         chatlog 的本地 HTTP 接口 127.0.0.1:5030（必须 format=json）
    wechatexporter  WechatExporter 导出的 HTML / TXT（iPhone 备份路线）
    telegram        Telegram Desktop 官方导出的 result.json
    whatsapp        WhatsApp「导出聊天」的 _chat.txt
    plain           一个目录里你自己写的东西（日记、笔记、草稿）——没有聊天记录也能用

用法：
    python3 adapters.py --source imessage --out ./work/raw.jsonl
    python3 adapters.py --source imessage --me-handle "+8613800000000" --out ./work/raw.jsonl
    python3 adapters.py --source chatlog --since 2019-01-01 --out ./work/raw.jsonl
    python3 adapters.py --source wechatexporter --input ~/Downloads/导出目录 --out ./work/raw.jsonl
    python3 adapters.py --source telegram --input result.json --out ./work/raw.jsonl
    python3 adapters.py --source plain --input ~/我的日记 --out ./work/raw.jsonl

然后：
    python3 extract_me.py --input ./work/raw.jsonl --out ./work
"""

import argparse
import glob
import html
import json
import os
import re
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta


def emit(fh, time_v, is_sender, content, talker):
    if content is None:
        return 0
    content = str(content).strip()
    if not content:
        return 0
    fh.write(json.dumps({
        "time": time_v, "is_sender": 1 if is_sender else 0,
        "content": content, "talker": str(talker or "未知"),
    }, ensure_ascii=False) + "\n")
    return 1


# ============================================================ iMessage（Mac 本地）

APPLE_EPOCH = datetime(2001, 1, 1)


def adapt_imessage(args, fh):
    """
    读 Mac 自带的信息数据库。这是全篇最省事、最合法、最不会失效的一条路：
    库就在你自己的硬盘上，苹果没有加密它，也没人对它发过 DMCA。
    唯一门槛是终端需要「完全磁盘访问权限」。
    """
    db = os.path.expanduser(args.input or "~/Library/Messages/chat.db")
    if not os.path.exists(db):
        print(f"[×] 找不到 {db}", file=sys.stderr)
        return 0
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    except sqlite3.OperationalError as e:
        print(f"[×] 打不开数据库：{e}", file=sys.stderr)
        return 0

    # 先探测列，不同 macOS 版本略有差异
    cols = {r[1] for r in con.execute("PRAGMA table_info(message)")}
    text_expr = "m.text"
    if "attributedBody" in cols:
        # 新版 macOS 有时把正文塞进 attributedBody，text 为空；这里只取 text 有值的
        pass

    sql = f"""
    SELECT m.date, m.is_from_me, {text_expr},
           COALESCE(c.display_name, c.chat_identifier, h.id, '未知') AS talker
    FROM message m
    LEFT JOIN handle h ON m.handle_id = h.ROWID
    LEFT JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
    LEFT JOIN chat c ON c.ROWID = cmj.chat_id
    WHERE m.text IS NOT NULL AND LENGTH(TRIM(m.text)) > 0
    ORDER BY m.date
    """
    n = 0
    for date_raw, is_me, text, talker in con.execute(sql):
        # Apple 的时间戳：2001-01-01 起的秒；新版是纳秒
        try:
            d = int(date_raw)
        except (TypeError, ValueError):
            continue
        if d > 10**12:
            d //= 10**9
        try:
            ts = (APPLE_EPOCH + timedelta(seconds=d)).strftime("%Y-%m-%d %H:%M:%S")
        except (OverflowError, OSError, ValueError):
            continue
        n += emit(fh, ts, is_me, text, talker)
    con.close()
    print(f"    信息数据库：{n:,} 条")
    return n


# ============================================================ chatlog HTTP 接口

def adapt_chatlog(args, fh):
    """
    chatlog 的本地接口。两个坑，两个都会让你白忙一场：
      1. CSV 导出**没有** isSelf 字段，必须用 format=json，否则你根本分不出谁说的。
      2. 微信 4.x 上 isSelf 是猜出来的（源码自己标了 FIXME 不准）。所以这里额外用
         「sender 是否等于我的 wxid」做交叉校验，两者不一致时按 --trust 决定信谁。
    """
    base = args.host.rstrip("/")
    since = args.since or "2000-01-01"
    until = args.until or datetime.now().strftime("%Y-%m-%d")
    q = urllib.parse.urlencode({
        "time": f"{since}~{until}", "talker": args.talker or "",
        "limit": str(args.limit), "offset": "0", "format": "json",
    })
    url = f"{base}/api/v1/chatlog?{q}"
    print(f"    请求 {url}")
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.URLError as e:
        print(f"[×] 连不上 chatlog：{e}\n    先确认 `chatlog server` 在跑，"
              f"默认地址 http://127.0.0.1:5030", file=sys.stderr)
        return 0
    except json.JSONDecodeError:
        print("[×] 返回的不是 JSON。确认 URL 里带了 format=json", file=sys.stderr)
        return 0

    if isinstance(data, dict):
        for k in ("items", "data", "messages", "list"):
            if isinstance(data.get(k), list):
                data = data[k]
                break
    if not isinstance(data, list):
        print("[×] 返回结构不认识", file=sys.stderr)
        return 0

    my = (args.me_handle or "").strip()
    n = disagree = 0
    for m in data:
        if not isinstance(m, dict):
            continue
        flag = bool(m.get("isSelf") or m.get("is_self") or m.get("IsSelf"))
        sender = str(m.get("sender") or m.get("Sender") or "")
        if my:
            cross = (sender == my)
            if cross != flag:
                disagree += 1
                flag = cross if args.trust == "sender" else flag
        n += emit(fh, m.get("time") or m.get("Time"), flag,
                  m.get("content") or m.get("Content"),
                  m.get("talker") or m.get("talkerName") or m.get("Talker"))
    print(f"    chatlog：{n:,} 条")
    if disagree:
        print(f"    [!] isSelf 与 sender 判断不一致 {disagree:,} 条（微信 4.x 已知问题），"
              f"当前按 --trust={args.trust} 处理")
    if len(data) >= args.limit:
        print(f"    [!] 返回条数已达 --limit={args.limit}，可能被截断。"
              f"建议按年份分批拉，或调大 --limit")
    return n


# ============================================================ WechatExporter

# HTML 输出里，自己发的消息在 BlueMatthew/WechatExporter 中带 des==0，
# 渲染成右对齐的一类 div；不同模板 class 名不同，这里都试一遍。
WE_HTML_ROW = re.compile(
    r'<div[^>]*class="[^"]*\b(?P<side>myself|self|right|s_r|sender)\b[^"]*"[^>]*>(?P<body>.*?)</div>\s*</div>',
    re.S | re.I)
WE_TIME = re.compile(r"(\d{4}[-/]\d{1,2}[-/]\d{1,2}[ T]\d{1,2}:\d{2}(?::\d{2})?)")
WE_TXT_LINE = re.compile(
    r"^(?P<name>.{0,40}?)\s*\((?P<ts>\d{4}[-/]\d{1,2}[-/]\d{1,2}[ T]?\s*\d{1,2}:\d{2}(?::\d{2})?)\)\s*[:：]?\s*(?P<body>.*)$")


def adapt_wechatexporter(args, fh):
    root = os.path.expanduser(args.input or ".")
    files = []
    for ext in ("html", "htm", "txt"):
        files += glob.glob(os.path.join(root, "**", f"*.{ext}"), recursive=True)
    if not files:
        print(f"[×] {root} 下没有 html/txt", file=sys.stderr)
        return 0
    if not args.me_handle:
        print("[!] 建议用 --me-handle 指定你在导出文件里显示的昵称，"
              "否则只能靠 HTML 的对齐样式判断，容易出错")

    n = 0
    for path in sorted(files):
        talker = os.path.splitext(os.path.basename(path))[0]
        try:
            raw = open(path, "r", encoding="utf-8", errors="ignore").read()
        except OSError:
            continue

        if path.lower().endswith(("html", "htm")):
            for m in WE_HTML_ROW.finditer(raw):
                body = re.sub(r"<[^>]+>", " ", m.group("body"))
                body = html.unescape(body)
                tm = WE_TIME.search(body)
                ts = tm.group(1) if tm else None
                if ts:
                    body = body.replace(ts, " ")
                n += emit(fh, ts, True, re.sub(r"\s+", " ", body).strip(), talker)
        else:
            cur_ts = cur_me = None
            buf = []
            for ln in raw.splitlines():
                m = WE_TXT_LINE.match(ln.strip())
                if m:
                    if cur_ts is not None and buf:
                        n += emit(fh, cur_ts, cur_me, "\n".join(buf), talker)
                    buf = [m.group("body")]
                    cur_ts = m.group("ts")
                    nm = m.group("name").strip()
                    cur_me = (nm == args.me_handle.strip()) if args.me_handle else None
                elif cur_ts is not None:
                    buf.append(ln)
            if cur_ts is not None and buf and cur_me is not None:
                n += emit(fh, cur_ts, cur_me, "\n".join(buf), talker)
    print(f"    WechatExporter：{n:,} 条（来自 {len(files)} 个文件）")
    if n == 0:
        print("[!] 一条都没解析出来。这个工具的模板版本很多，"
              "请把一个导出文件的前 40 行贴出来，好补一个解析规则")
    return n


# ============================================================ Telegram

def adapt_telegram(args, fh):
    path = os.path.expanduser(args.input or "result.json")
    if not os.path.exists(path):
        print(f"[×] 找不到 {path}", file=sys.stderr)
        return 0
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    me_id = None
    if isinstance(data, dict):
        pi = data.get("personal_information") or {}
        if pi.get("user_id"):
            me_id = f"user{pi['user_id']}"
    chats = []
    if isinstance(data, dict):
        cl = data.get("chats", {})
        chats = cl.get("list", []) if isinstance(cl, dict) else (cl or [])
        if not chats and "messages" in data:
            chats = [data]

    def flat(txt):
        if isinstance(txt, str):
            return txt
        if isinstance(txt, list):
            return "".join(x if isinstance(x, str) else x.get("text", "") for x in txt)
        return ""

    n = 0
    for ch in chats:
        talker = ch.get("name") or ch.get("id") or "未知"
        for m in ch.get("messages", []):
            if m.get("type") != "message":
                continue
            frm = m.get("from_id") or ""
            is_me = (frm == me_id) if me_id else (
                m.get("from") == args.me_handle if args.me_handle else False)
            n += emit(fh, m.get("date"), is_me, flat(m.get("text")), talker)
    print(f"    Telegram：{n:,} 条")
    if me_id is None and not args.me_handle:
        print("[!] 导出里没有 personal_information，无法确定哪条是你发的。"
              "请加 --me-handle 你的 Telegram 显示名")
    return n


# ============================================================ WhatsApp

WA_LINE = re.compile(
    r"^\[?(?P<ts>\d{1,4}[-/]\d{1,2}[-/]\d{1,4},?\s+\d{1,2}:\d{2}(?::\d{2})?(?:\s*[APap][Mm])?)\]?\s*[-–]?\s*(?P<name>[^:]{1,40}):\s(?P<body>.*)$")


def adapt_whatsapp(args, fh):
    root = os.path.expanduser(args.input or ".")
    files = [root] if os.path.isfile(root) else glob.glob(
        os.path.join(root, "**", "*.txt"), recursive=True)
    if not args.me_handle:
        print("[×] WhatsApp 导出里只有显示名，必须用 --me-handle 指定你自己的名字",
              file=sys.stderr)
        return 0
    n = 0
    for path in files:
        talker = os.path.splitext(os.path.basename(path))[0]
        cur = None
        for ln in open(path, "r", encoding="utf-8", errors="ignore"):
            m = WA_LINE.match(ln.rstrip("\n"))
            if m:
                if cur:
                    n += emit(fh, cur[0], cur[1], "\n".join(cur[2]), talker)
                cur = (m.group("ts"),
                       m.group("name").strip() == args.me_handle.strip(),
                       [m.group("body")])
            elif cur:
                cur[2].append(ln.rstrip("\n"))
        if cur:
            n += emit(fh, cur[0], cur[1], "\n".join(cur[2]), talker)
    print(f"    WhatsApp：{n:,} 条")
    return n


# ============================================================ 纯文本（兜底）

DATE_IN_NAME = re.compile(r"(20\d{2})[-_.]?(\d{2})[-_.]?(\d{2})")


def adapt_plain(args, fh):
    """
    没有任何聊天记录也能用这个 skill：把你自己写过的东西喂进来。
    日记、笔记、备忘录、公众号草稿、发出去的邮件、朋友圈存档，都算数。
    文件名或正文里第一个日期作为时间；整篇算一条（超过 --split-chars 会按段落切）。
    """
    root = os.path.expanduser(args.input or ".")
    files = []
    for ext in ("md", "txt", "markdown"):
        files += glob.glob(os.path.join(root, "**", f"*.{ext}"), recursive=True)
    if not files:
        print(f"[×] {root} 下没有 md/txt", file=sys.stderr)
        return 0
    n = 0
    for path in sorted(files):
        base = os.path.basename(path)
        raw = open(path, "r", encoding="utf-8", errors="ignore").read()
        m = DATE_IN_NAME.search(base) or DATE_IN_NAME.search(raw[:400])
        if m:
            ts = f"{m.group(1)}-{m.group(2)}-{m.group(3)} 12:00:00"
        else:
            ts = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M:%S")
        talker = os.path.basename(os.path.dirname(path)) or "自述"
        for para in re.split(r"\n\s*\n", raw):
            para = para.strip()
            if len(para) >= 10:
                n += emit(fh, ts, True, para, talker)
    print(f"    纯文本：{n:,} 段（来自 {len(files)} 个文件）")
    return n


# ============================================================

ADAPTERS = {
    "imessage": adapt_imessage,
    "chatlog": adapt_chatlog,
    "wechatexporter": adapt_wechatexporter,
    "telegram": adapt_telegram,
    "whatsapp": adapt_whatsapp,
    "plain": adapt_plain,
}


def main():
    ap = argparse.ArgumentParser(
        description="把各种来源的聊天记录转成统一中间格式",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    ap.add_argument("--source", required=True, choices=sorted(ADAPTERS))
    ap.add_argument("--input", default=None, help="文件或目录（imessage / chatlog 可省略）")
    ap.add_argument("--out", default="./work/raw.jsonl")
    ap.add_argument("--me-handle", default=None,
                    help="你自己的标识：昵称 / wxid / 手机号，取决于来源")
    ap.add_argument("--host", default="http://127.0.0.1:5030", help="chatlog 地址")
    ap.add_argument("--talker", default=None, help="chatlog：只拉某个会话")
    ap.add_argument("--since", default=None)
    ap.add_argument("--until", default=None)
    ap.add_argument("--limit", type=int, default=200000, help="chatlog 单次拉取上限")
    ap.add_argument("--trust", default="sender", choices=["sender", "flag"],
                    help="chatlog：isSelf 与 sender 冲突时信谁（微信 4.x 建议 sender）")
    args = ap.parse_args()

    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    print(f"[·] 来源：{args.source}")
    with open(args.out, "w", encoding="utf-8") as fh:
        n = ADAPTERS[args.source](args, fh)

    if n:
        print(f"\n[✓] {args.out}（{n:,} 条，含别人说的）")
        print(f"    下一步：python3 extract_me.py --input {args.out} --out "
              f"{os.path.dirname(args.out) or '.'}")
        return 0
    print("\n[×] 没有产出任何数据", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
