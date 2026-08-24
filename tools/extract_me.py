#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_me.py —— 从任意微信导出文件里，只把「我自己说过的话」捞出来。

设计原则：
  1. 只留自己的话。别人的一个字都不进后续流程——这既是分析方法，也是对别人的隐私保护。
  2. 联系人一律脱敏成代号。真名与代号的对照表单独存一份，永不进入分析语料。
  3. 零第三方依赖，只用标准库。装个包都要联网的工具，不配处理这种数据。
  4. 列名自动识别 + 手动覆盖。各家导出工具字段名不同，先猜，猜错了让人改。

用法：
    # 先看看认出了什么，不写文件
    python3 extract_me.py --input 导出目录或文件 --probe

    # 正式跑
    python3 extract_me.py --input ./export --out ./work

    # 字段认错了，手动指定
    python3 extract_me.py --input a.csv --out ./work \\
        --field-time CreateTime --field-me IsSender --field-text StrContent --field-contact talker

输出（全部落在 --out 目录）：
    me.jsonl        分析用语料：只有我说的话，联系人已脱敏
    contacts.json   代号 → 统计信息（不含真名）
    NAMEMAP.local.json   代号 ↔ 真名 对照表【本地私有，默认已加进 .gitignore，别外传】
    extract_report.txt   这次提取干了什么，丢了多少，为什么丢
"""

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

# ---------------------------------------------------------------- 字段猜测表

# 时间字段：值可能是 unix 秒 / 毫秒 / 字符串日期
TIME_KEYS = [
    "CreateTime", "createTime", "create_time", "msgCreateTime", "msgTime",
    "StrTime", "strTime", "time", "timestamp", "date", "datetime", "Date",
    "发送时间", "时间",
]

# 「这条是我发的吗」字段
ME_KEYS = [
    "IsSender", "is_sender", "isSender", "isSend", "is_send", "IsSend",
    "is_self", "isSelf", "self", "direction", "Direction", "sender_type",
    "fromMe", "from_me", "是否自己发送", "发送方",
]

# 正文
TEXT_KEYS = [
    "StrContent", "strContent", "content", "Content", "msg", "message",
    "Message", "text", "Text", "body", "内容", "消息内容", "正文",
]

# 聊天对象 / 会话
CONTACT_KEYS = [
    "talker", "Talker", "NickName", "nickname", "remark", "Remark",
    "chat_name", "chatName", "room_name", "roomName", "UserName", "username",
    "wxid", "sender", "Sender", "对方", "聊天对象", "昵称", "群名",
]

# 消息类型（1 通常是文本）
TYPE_KEYS = ["Type", "type", "MsgType", "msgType", "msg_type", "消息类型"]

# 发送者名字（用于 TXT 格式与「谁说的」判断）
SENDER_NAME_KEYS = ["NickName", "sender_name", "senderName", "speaker", "发送人", "发送者"]


def _norm(s):
    return re.sub(r"[\s_\-]+", "", str(s)).lower()


def guess_key(fieldnames, candidates):
    """在真实列名里找候选字段，先精确后模糊。"""
    if not fieldnames:
        return None
    exact = {f: f for f in fieldnames}
    for c in candidates:
        if c in exact:
            return c
    normmap = {_norm(f): f for f in fieldnames}
    for c in candidates:
        if _norm(c) in normmap:
            return normmap[_norm(c)]
    for c in candidates:
        nc = _norm(c)
        for nf, f in normmap.items():
            if nc and (nc in nf or nf in nc):
                return f
    return None


# ---------------------------------------------------------------- 值的解析

_TRUE_SET = {"1", "true", "yes", "y", "是", "self", "me", "send", "发送", "我"}
_FALSE_SET = {"0", "false", "no", "n", "否", "other", "recv", "receive", "接收", "对方"}


def parse_is_me(raw, me_true_values=None):
    """把五花八门的『是我发的』表示统一成 True/False/None。"""
    if raw is None:
        return None
    v = str(raw).strip().lower()
    if me_true_values:
        return v in {x.strip().lower() for x in me_true_values}
    if v in _TRUE_SET:
        return True
    if v in _FALSE_SET:
        return False
    return None


_DATE_PATTERNS = [
    "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M", "%Y-%m-%d", "%Y/%m/%d",
    "%Y年%m月%d日 %H:%M:%S", "%Y年%m月%d日 %H:%M",
]


def parse_time(raw):
    """→ 本地时间的 datetime，认不出返回 None。"""
    if raw is None or raw == "":
        return None
    s = str(raw).strip()
    if re.fullmatch(r"\d{9,20}", s):
        n = int(s)
        if n > 10_000_000_000_000:      # 微秒
            n //= 1_000_000
        elif n > 10_000_000_000:        # 毫秒
            n //= 1000
        if not (10**8 < n < 4 * 10**9):
            return None
        try:
            return datetime.fromtimestamp(n)
        except (OSError, OverflowError, ValueError):
            return None
    s2 = s.replace("T", " ").split("+")[0].split(".")[0].strip()
    for p in _DATE_PATTERNS:
        try:
            return datetime.strptime(s2, p)
        except ValueError:
            continue
    return None


# ------------------------------------------------------- 正文清洗（很重要）

# 这些不是「你说的话」，是客户端替你说的。留着会污染所有词频统计。
NOISE_PATTERNS = [
    (re.compile(r"^\s*$"), "空"),
    (re.compile(r"^<\?xml", re.I), "XML消息(卡片/引用/文件)"),
    (re.compile(r"^<msg[\s>]", re.I), "XML消息"),
    (re.compile(r"^\[(图片|表情|动画表情|语音|视频|文件|位置|名片|链接|小程序|转账|红包|音乐|视频通话|语音通话|拍一拍|聊天记录|收藏|直播|视频号)\]?"), "非文本消息"),
    (re.compile(r"^(图片|视频|语音|动画表情|文件)$"), "非文本消息"),
    (re.compile(r"^wxid_\w+$"), "系统标识"),
    (re.compile(r"^https?://\S+$"), "纯链接"),
    (re.compile(r"^(你已添加了|以上是打招呼的内容|我通过了你的朋友验证请求|对方开启了朋友验证|你撤回了一条消息|.{0,20}撤回了一条消息|该消息类型暂不能展示|请在手机上查看|收到红包|微信转账|你已成功领取)"), "系统提示"),
    (re.compile(r"^\s*[\[【]?(收到转账|已收款|微信支付|安全提示)"), "系统提示"),
]

# 行内噪声：删掉但保留整条
INLINE_CLEANERS = [
    (re.compile(r"\[(?:害羞|微笑|捂脸|偷笑|笑哭|旺柴|皱眉|流泪|发呆|得意|大哭|尴尬|发怒|调皮|呲牙|惊讶|难过|酷|冷汗|抓狂|吐|偷笑|愉快|白眼|傲慢|困|惊恐|憨笑|悠闲|咒骂|疑问|嘘|晕|衰|骷髅|敲打|再见|擦汗|抠鼻|鼓掌|坏笑|左哼哼|右哼哼|哈欠|鄙视|委屈|快哭了|阴险|亲亲|可怜|菜刀|西瓜|啤酒|咖啡|猪头|玫瑰|凋谢|嘴唇|爱心|心碎|蛋糕|炸弹|便便|月亮|太阳|拥抱|强|弱|握手|胜利|抱拳|勾引|拳头|OK|合十|加油|庆祝|礼物|red packet|发红包|烟花|爆竹|福|哇|嘿哈|捂脸|奸笑|机智|加油|囧|吃瓜|加油加油|汗|天啊|Emm|social|旺柴|好的|打脸|哇哦|翻白眼|666|让我看看|叹气|苦涩|裂开)\]"), ""),
    (re.compile(r"https?://\S+"), " <链接> "),
    (re.compile(r"@[一-龥\w\-]{1,20}\s"), " "),  # 群里 @人
    (re.compile(r"\s+"), " "),
]


def clean_text(t):
    """返回 (清洗后的文本, 丢弃原因或 None)。"""
    if t is None:
        return "", "空"
    t = str(t).strip()
    for pat, reason in NOISE_PATTERNS:
        if pat.search(t):
            return "", reason
    for pat, rep in INLINE_CLEANERS:
        t = pat.sub(rep, t)
    t = t.strip()
    if not t:
        return "", "清洗后为空"
    # 纯符号 / 纯数字，无信息量
    if not re.search(r"[一-龥a-zA-Z]", t):
        return "", "无文字内容"
    return t, None


# ---------------------------------------------------------------- 脱敏

class Anonymizer:
    """真名 → 稳定代号。同一个人每次跑都是同一个代号，跨次运行可比。"""

    def __init__(self, salt="juexing"):
        self.salt = salt
        self.map = {}            # 真名 -> 代号
        self.reverse = {}        # 代号 -> 真名
        self._counters = Counter()

    def code(self, raw_name, is_group=False):
        raw_name = (raw_name or "未知").strip() or "未知"
        if raw_name in self.map:
            return self.map[raw_name]
        prefix = "群" if is_group else "人"
        h = hashlib.sha1((self.salt + raw_name).encode("utf-8")).hexdigest()[:4]
        self._counters[prefix] += 1
        code = f"{prefix}{self._counters[prefix]:03d}-{h}"
        self.map[raw_name] = code
        self.reverse[code] = raw_name
        return code


def looks_like_group(name):
    if not name:
        return False
    return "@chatroom" in str(name) or str(name).endswith("@im.chatroom")


# ---------------------------------------------------------------- 读入

def iter_csv(path):
    for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030", "latin-1"):
        try:
            with open(path, "r", encoding=enc, newline="") as f:
                sample = f.read(8192)
                f.seek(0)
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
                except csv.Error:
                    dialect = csv.excel
                reader = csv.DictReader(f, dialect=dialect)
                rows = list(reader)
            if rows:
                return rows, reader.fieldnames, enc
        except (UnicodeDecodeError, csv.Error):
            continue
        except Exception:
            continue
    return [], None, None


def iter_json(path):
    """整份 JSON 与逐行 JSONL 都要认。先试整份，失败再逐行——
    .jsonl 的第一个字符也是 `{`，光看开头会认错。"""
    for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
        try:
            with open(path, "r", encoding=enc) as f:
                raw = f.read()
        except UnicodeDecodeError:
            continue

        data = None
        try:                                   # 情况一：整份是一个 JSON
            data = json.loads(raw)
            if isinstance(data, dict):
                for k in ("messages", "data", "list", "records", "msgs", "items"):
                    if isinstance(data.get(k), list):
                        data = data[k]
                        break
                else:
                    data = [data]
        except json.JSONDecodeError:           # 情况二：一行一个 JSON
            data = []
            for ln in raw.splitlines():
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    data.append(json.loads(ln))
                except json.JSONDecodeError:
                    continue

        try:
            data = [d for d in (data or []) if isinstance(d, dict)]
            if data:
                keys = []
                for d in data[:200]:
                    for k in d:
                        if k not in keys:
                            keys.append(k)
                return data, keys, enc
        except Exception:
            continue
    return [], None, None


# TXT 格式：「昵称 2023-05-01 12:00:00\n内容」或「2023-05-01 12:00:00 昵称: 内容」
TXT_HEAD = re.compile(
    r"^(?P<a>.{0,40}?)\s*(?P<ts>\d{4}[-/]\d{1,2}[-/]\d{1,2}[ T]\d{1,2}:\d{2}(?::\d{2})?)\s*(?P<b>.{0,40}?)\s*[:：]?\s*$"
)


def iter_txt(path):
    """兜底解析器。只能靠『发送者名字 == 我的昵称』来判断，需要 --my-name。"""
    rows = []
    for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
        try:
            with open(path, "r", encoding=enc) as f:
                lines = f.read().splitlines()
            break
        except UnicodeDecodeError:
            continue
    else:
        return [], None, None

    cur = None
    for ln in lines:
        m = TXT_HEAD.match(ln.strip())
        if m:
            if cur:
                rows.append(cur)
            name = (m.group("a") or m.group("b") or "").strip(" :：")
            cur = {"time": m.group("ts"), "sender_name": name, "content": ""}
        elif cur is not None:
            cur["content"] = (cur["content"] + "\n" + ln).strip()
    if cur:
        rows.append(cur)
    return rows, ["time", "sender_name", "content"], enc


def collect_files(root, exts=(".csv", ".json", ".jsonl", ".txt")):
    if os.path.isfile(root):
        return [root]
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for fn in sorted(filenames):
            if fn.startswith("."):
                continue
            if os.path.splitext(fn)[1].lower() in exts:
                out.append(os.path.join(dirpath, fn))
    return sorted(out)


# ---------------------------------------------------------------- 主流程

def main():
    ap = argparse.ArgumentParser(
        description="从微信导出文件中提取『只有我说过的话』并脱敏",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, help="导出的文件或目录")
    ap.add_argument("--out", default="./work", help="输出目录（默认 ./work）")
    ap.add_argument("--probe", action="store_true", help="只报告识别结果，不写文件")
    ap.add_argument("--my-name", default=None,
                    help="我的微信昵称。TXT 格式必须给；其他格式在没有 is_sender 字段时作为兜底")
    ap.add_argument("--field-time", default=None)
    ap.add_argument("--field-me", default=None)
    ap.add_argument("--field-text", default=None)
    ap.add_argument("--field-contact", default=None)
    ap.add_argument("--field-type", default=None)
    ap.add_argument("--me-true", default=None,
                    help="『是我发的』那一列取什么值代表是我，逗号分隔，例如 1 或 send")
    ap.add_argument("--since", default=None, help="只要这个日期之后的，格式 YYYY-MM-DD")
    ap.add_argument("--until", default=None, help="只要这个日期之前的，格式 YYYY-MM-DD")
    ap.add_argument("--exclude-groups", action="store_true", help="排除群聊，只留一对一")
    ap.add_argument("--min-len", type=int, default=2, help="短于这个字数的消息丢掉（默认 2）")
    ap.add_argument("--salt", default="juexing", help="脱敏代号的盐值，换了代号就变")
    args = ap.parse_args()

    files = collect_files(args.input)
    if not files:
        print(f"[×] {args.input} 下没找到 .csv/.json/.jsonl/.txt 文件", file=sys.stderr)
        return 2

    since = parse_time(args.since) if args.since else None
    until = parse_time(args.until) if args.until else None
    me_true = args.me_true.split(",") if args.me_true else None

    anon = Anonymizer(args.salt)
    records = []
    drops = Counter()
    probe_lines = []
    files_used = 0

    for path in files:
        ext = os.path.splitext(path)[1].lower()
        if ext == ".csv":
            rows, fields, enc = iter_csv(path)
        elif ext in (".json", ".jsonl"):
            rows, fields, enc = iter_json(path)
        else:
            rows, fields, enc = iter_txt(path)

        if not rows:
            probe_lines.append(f"  ✗ {os.path.basename(path)} —— 读不出内容，跳过")
            continue

        k_time = args.field_time or guess_key(fields, TIME_KEYS)
        k_me = args.field_me or guess_key(fields, ME_KEYS)
        k_text = args.field_text or guess_key(fields, TEXT_KEYS)
        k_contact = args.field_contact or guess_key(fields, CONTACT_KEYS)
        k_type = args.field_type or guess_key(fields, TYPE_KEYS)
        k_sender = guess_key(fields, SENDER_NAME_KEYS)

        probe_lines.append(
            f"  · {os.path.basename(path)}  [{enc}] {len(rows)} 行\n"
            f"      时间={k_time}  是我={k_me}  正文={k_text}  对象={k_contact}  类型={k_type}\n"
            f"      全部列名: {', '.join(map(str, fields or []))[:300]}")

        if not k_text:
            drops["找不到正文列"] += len(rows)
            continue

        # 文件名常常就是聊天对象（chatlog / WeChatMsg 按会话导出时）
        fallback_contact = os.path.splitext(os.path.basename(path))[0]

        for r in rows:
            # --- 是不是我说的 ---
            is_me = None
            if k_me:
                is_me = parse_is_me(r.get(k_me), me_true)
            if is_me is None and args.my_name:
                nm = r.get(k_sender) or r.get("sender_name") or ""
                if nm:
                    is_me = str(nm).strip() == args.my_name.strip()
            if is_me is None:
                drops["判断不出是谁说的"] += 1
                continue
            if not is_me:
                drops["别人说的（按设计丢弃）"] += 1
                continue

            # --- 类型过滤 ---
            if k_type:
                tv = str(r.get(k_type, "")).strip()
                if tv and tv not in ("1", "text", "Text", "文本", ""):
                    drops[f"非文本类型({tv})"] += 1
                    continue

            # --- 正文 ---
            txt, why = clean_text(r.get(k_text))
            if why:
                drops[why] += 1
                continue
            if len(txt) < args.min_len:
                drops["太短"] += 1
                continue

            # --- 时间 ---
            dt = parse_time(r.get(k_time)) if k_time else None
            if dt is None:
                drops["时间认不出"] += 1
                continue
            if since and dt < since:
                drops["早于 --since"] += 1
                continue
            if until and dt > until:
                drops["晚于 --until"] += 1
                continue

            # --- 对象 ---
            raw_contact = str(r.get(k_contact) or fallback_contact).strip()
            grp = looks_like_group(raw_contact) or raw_contact.startswith("群")
            if args.exclude_groups and grp:
                drops["群聊（--exclude-groups）"] += 1
                continue
            code = anon.code(raw_contact, grp)

            records.append({
                "ts": dt.strftime("%Y-%m-%d %H:%M:%S"),
                "y": dt.year, "m": dt.month, "hour": dt.hour,
                "wd": dt.weekday(),
                "to": code,
                "grp": grp,
                "n": len(txt),
                "t": txt,
            })
        files_used += 1

    records.sort(key=lambda x: x["ts"])

    # ---------------- 报告 ----------------
    lines = []
    lines.append("=" * 60)
    lines.append("提取报告")
    lines.append("=" * 60)
    lines.append(f"扫描文件 {len(files)} 个，成功解析 {files_used} 个")
    lines.extend(probe_lines)
    lines.append("")
    lines.append(f"【保留】我自己说的话 {len(records):,} 条")
    if records:
        lines.append(f"       时间跨度 {records[0]['ts'][:10]} → {records[-1]['ts'][:10]}")
        lines.append(f"       总字数 {sum(r['n'] for r in records):,}")
        lines.append(f"       聊天对象 {len(set(r['to'] for r in records))} 个"
                     f"（其中群 {len(set(r['to'] for r in records if r['grp']))} 个）")
    lines.append("")
    lines.append("【丢弃】")
    for reason, cnt in drops.most_common():
        lines.append(f"       {cnt:>9,}  {reason}")
    report = "\n".join(lines)
    print(report)

    if args.probe:
        print("\n（--probe 模式，没有写任何文件。字段认错了就用 --field-* 手动指定。）")
        return 0

    if not records:
        print("\n[×] 一条都没提取到。多半是『是我发的』那一列没认出来。"
              "\n    先跑一次 --probe 看列名，再用 --field-me / --me-true 指定。", file=sys.stderr)
        return 1

    os.makedirs(args.out, exist_ok=True)

    me_path = os.path.join(args.out, "me.jsonl")
    with open(me_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # 联系人统计（不含真名）
    per = defaultdict(lambda: {"count": 0, "chars": 0, "first": None, "last": None, "grp": False})
    for r in records:
        d = per[r["to"]]
        d["count"] += 1
        d["chars"] += r["n"]
        d["grp"] = r["grp"]
        d["first"] = d["first"] or r["ts"][:10]
        d["last"] = r["ts"][:10]
    with open(os.path.join(args.out, "contacts.json"), "w", encoding="utf-8") as f:
        json.dump(dict(sorted(per.items(), key=lambda kv: -kv[1]["count"])),
                  f, ensure_ascii=False, indent=2)

    # 真名对照表：本地私有
    nm_path = os.path.join(args.out, "NAMEMAP.local.json")
    with open(nm_path, "w", encoding="utf-8") as f:
        json.dump(anon.reverse, f, ensure_ascii=False, indent=2)
    try:
        os.chmod(nm_path, 0o600)
    except OSError:
        pass

    gi = os.path.join(args.out, ".gitignore")
    if not os.path.exists(gi):
        with open(gi, "w", encoding="utf-8") as f:
            f.write("*\n!.gitignore\n")

    with open(os.path.join(args.out, "extract_report.txt"), "w", encoding="utf-8") as f:
        f.write(report + "\n")

    print(f"\n[✓] {me_path}")
    print(f"[✓] {os.path.join(args.out, 'contacts.json')}")
    print(f"[!] {nm_path} —— 真名对照表，权限已设为 600，不要外传、不要进 git、不要贴给模型")
    return 0


if __name__ == "__main__":
    sys.exit(main())
