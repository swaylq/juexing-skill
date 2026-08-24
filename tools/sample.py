#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sample.py —— 从几万条自己说过的话里，挑出该被读的那几百句。

为什么需要这一步：
    八年的聊天记录塞不进任何模型的上下文。随便截一段又会让结论取决于你截了哪一段。
    这个脚本做分层抽样：每一年、每一类信号、每一个重要的人，都保证有代表进入语料，
    并且明确告诉你「哪些被抽中、按什么规则抽的、覆盖率是多少」。
    抽样规则写在输出文件的开头，谁都可以质疑它。

    另外它做一件更重要的事：**把该保护的东西挡在外面**。
    默认脱敏手机号、身份证、银行卡、邮箱、具体住址门牌，并支持 --redact 追加自定义关键词。

用法：
    python3 sample.py --in ./work/me.jsonl --stats ./work/stats.json --out ./work
    python3 sample.py --in ./work/me.jsonl --per-year 40 --redact 公司名,某人真名
产出：
    corpus.md      分层抽样后的原话，带日期与脱敏代号——这是模型唯一能看到的原始语料
    sampling.json  抽样规则与覆盖率，用来检查有没有被抽样偏差骗了
"""

import argparse
import json
import os
import random
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from stats import LEX
except ImportError:
    LEX = {}

# ---------------------------------------------------------------- 敏感信息屏蔽

REDACTORS = [
    (re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "<手机号>"),
    (re.compile(r"(?<!\d)\d{15}(?:\d{2}[\dXx])?(?!\d)"), "<身份证>"),
    (re.compile(r"(?<!\d)\d{16,19}(?!\d)"), "<卡号>"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "<邮箱>"),
    (re.compile(r"https?://\S+"), "<链接>"),
    (re.compile(r"\d+\s*(?:栋|幢|单元|楼|室|号楼|号院)"), "<门牌>"),
    (re.compile(r"(?<!\d)\d{6}(?!\d)\s*(?:邮编)"), "<邮编>"),
    (re.compile(r"(?:密码|验证码|口令)\s*[:：是]?\s*\S{4,20}"), "<凭据已删除>"),
]


def redact(text, extra_terms):
    for pat, rep in REDACTORS:
        text = pat.sub(rep, text)
    for t in extra_terms:
        t = t.strip()
        if t:
            text = text.replace(t, "<已隐去>")
    return text


# ---------------------------------------------------------------- 打标签

def tag(text):
    """给一条消息打上它命中的信号标签。"""
    tags = []
    for k, words in LEX.items():
        if any(w in text for w in words):
            tags.append(k)
    return tags


def load(path):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                rows.append(json.loads(ln))
    return rows


def pick(pool, n, rng, taken):
    """从 pool 里挑 n 条没被挑过的，长的优先但保留随机性。"""
    cand = [r for r in pool if id(r) not in taken]
    if not cand:
        return []
    # 一半按信息量（长度）挑，一半随机——避免全是长篇大论，也避免全是「嗯」
    cand_sorted = sorted(cand, key=lambda r: -r["n"])
    top = cand_sorted[:max(1, n // 2)]
    rest = [r for r in cand if id(r) not in {id(x) for x in top}]
    rng.shuffle(rest)
    out = top + rest[:n - len(top)]
    for r in out:
        taken.add(id(r))
    return out


def main():
    ap = argparse.ArgumentParser(description="分层抽样：挑出该被读的那几百句")
    ap.add_argument("--in", dest="inp", default="./work/me.jsonl")
    ap.add_argument("--stats", default="./work/stats.json")
    ap.add_argument("--out", default="./work")
    ap.add_argument("--per-year", type=int, default=35, help="每年抽多少条基线样本")
    ap.add_argument("--per-signal", type=int, default=14, help="每类信号词抽多少条")
    ap.add_argument("--per-contact", type=int, default=10, help="每个重要联系人抽多少条")
    ap.add_argument("--top-contacts", type=int, default=8, help="取前几个联系人")
    ap.add_argument("--min-len", type=int, default=8, help="抽样时忽略过短的消息")
    ap.add_argument("--max-chars", type=int, default=300, help="单条最多保留多少字")
    ap.add_argument("--redact", default="", help="额外要隐去的词，逗号分隔（公司名、真名等）")
    ap.add_argument("--seed", type=int, default=20260825)
    args = ap.parse_args()

    if not os.path.exists(args.inp):
        print(f"[×] 找不到 {args.inp}", file=sys.stderr)
        return 2

    rng = random.Random(args.seed)
    rows = load(args.inp)
    rows = [r for r in rows if r["n"] >= args.min_len]
    if not rows:
        print("[×] 过滤后没有可用消息", file=sys.stderr)
        return 1

    extra = [t for t in args.redact.split(",") if t.strip()]
    taken = set()
    buckets = []      # (标题, 说明, [消息])

    by_year = defaultdict(list)
    for r in rows:
        by_year[r["y"]].append(r)

    # ---- 1. 逐年基线 ----
    for y in sorted(by_year):
        got = pick(by_year[y], args.per_year, rng, taken)
        buckets.append((f"{y} 年", f"从这一年 {len(by_year[y]):,} 条里随机与长文各半抽取", got))

    # ---- 2. 深夜 ----
    night = [r for r in rows if r["hour"] < 6]
    if night:
        buckets.append(("深夜 0–5 点说的话",
                        f"共 {len(night):,} 条。夜里说的话通常是白天不说的那些",
                        pick(night, 30, rng, taken)))

    # ---- 3. 每类信号 ----
    signal_order = ["自贬", "认输", "义务", "意愿", "从众", "自欺", "延宕", "立誓",
                    "焦虑", "抑郁", "疲惫", "孤独", "愤怒", "悲伤", "羞耻", "正面",
                    "道歉", "讨好", "拒绝", "批评", "蔑视", "防御", "筑墙", "过去", "未来"]
    for k in signal_order:
        if k not in LEX:
            continue
        pool = [r for r in rows if any(w in r["t"] for w in LEX[k])]
        if len(pool) < 3:
            continue
        got = pick(pool, args.per_signal, rng, taken)
        if got:
            buckets.append((f"信号：{k}",
                            f"全语料命中 {len(pool):,} 条，抽 {len(got)} 条",
                            got))

    # ---- 4. 重要联系人 ----
    by_to = defaultdict(list)
    for r in rows:
        by_to[r["to"]].append(r)
    top = sorted(by_to.items(), key=lambda kv: -len(kv[1]))[:args.top_contacts]
    for code, rs in top:
        got = pick(rs, args.per_contact, rng, taken)
        if got:
            yrs = sorted({x["y"] for x in rs})
            buckets.append((f"对 {code} 说的话",
                            f"共 {len(rs):,} 条，活跃于 {yrs[0]}–{yrs[-1]}",
                            got))

    # ---- 5. 最长的话 ----
    longest = sorted(rows, key=lambda r: -r["n"])[:20]
    got = [r for r in longest if id(r) not in taken][:12]
    for r in got:
        taken.add(id(r))
    if got:
        buckets.append(("写得最长的几条",
                        "一个人愿意写这么长，说明那件事对他重要", got))

    # ---- 6. 转折点前后 ----
    shift_years = []
    if os.path.exists(args.stats):
        try:
            with open(args.stats, "r", encoding="utf-8") as f:
                S = json.load(f)
            for s in S.get("年度突变候选", [])[:6]:
                shift_years.append(int(s["到年"]))
        except Exception:
            pass
    for y in sorted(set(shift_years)):
        pool = [r for r in by_year.get(y, []) if r["n"] >= 20]
        got = pick(pool, 18, rng, taken)
        if got:
            buckets.append((f"{y} 年（数字层标出的突变年）",
                            "统计上这一年出现了明显跳变，额外多抽一些原话来核对", got))

    # ---------------------------------------------------------------- 输出
    total_sampled = sum(len(b[2]) for b in buckets)
    L = []
    A = L.append
    A("# 原话样本")
    A("")
    A("> 下面每一句都是**我自己**说的，别人说的话一个字都没有进来。")
    A("> 联系人已替换成代号；手机号 / 身份证 / 卡号 / 邮箱 / 链接 / 门牌已自动隐去。")
    A("")
    A("## 抽样规则（请连规则一起质疑）")
    A("")
    A(f"- 总语料 {len(rows):,} 条（已剔除短于 {args.min_len} 字的），抽出 **{total_sampled} 条**，"
      f"抽样率 {total_sampled / len(rows):.2%}")
    A(f"- 每年基线 {args.per_year} 条；每类信号词 {args.per_signal} 条；"
      f"前 {args.top_contacts} 个联系人各 {args.per_contact} 条")
    A(f"- 每格内一半按长度取（信息量大），一半随机取（防止只看见长篇大论）")
    A(f"- 随机种子 {args.seed}，同一份数据重跑结果一致")
    A(f"- 单条超过 {args.max_chars} 字的会被截断，截断处标 `……`")
    A("")
    A("**已知的抽样偏差**：信号词分层会让带情绪的句子在样本里的比例高于它在真实语料里的比例。"
      "判断「他是不是经常焦虑」时，请看数字层的每千字频率，不要数这里出现了几条。")
    A("")
    A("---")
    A("")

    for title, desc, msgs in buckets:
        if not msgs:
            continue
        A(f"## {title}")
        A("")
        A(f"_{desc}_")
        A("")
        for r in sorted(msgs, key=lambda x: x["ts"]):
            t = redact(r["t"], extra)
            if len(t) > args.max_chars:
                t = t[:args.max_chars] + "……"
            t = t.replace("\n", " ")
            tg = tag(r["t"])
            tgs = f"  `{'/'.join(tg[:3])}`" if tg else ""
            A(f"- `{r['ts'][:10]} {r['ts'][11:16]}` → **{r['to']}**：{t}{tgs}")
        A("")

    md = "\n".join(L)
    os.makedirs(args.out, exist_ok=True)
    cp = os.path.join(args.out, "corpus.md")
    with open(cp, "w", encoding="utf-8") as f:
        f.write(md + "\n")

    meta = {
        "语料总数": len(rows),
        "抽出条数": total_sampled,
        "抽样率": round(total_sampled / len(rows), 4),
        "分组数": len(buckets),
        "参数": vars(args),
        "各组": [{"组": b[0], "条数": len(b[2])} for b in buckets],
    }
    with open(os.path.join(args.out, "sampling.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"[✓] {cp}")
    print(f"    {len(buckets)} 组 / {total_sampled} 条 / 抽样率 {total_sampled / len(rows):.2%}")
    print(f"    约 {len(md) // 2:,} token 量级，请确认能装进上下文")
    return 0


if __name__ == "__main__":
    sys.exit(main())
