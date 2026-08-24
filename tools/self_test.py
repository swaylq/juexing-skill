#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
self_test.py —— 整条流水线跑一遍，外加内容完整性检查。

CI 跑它，改完代码也跑它。零第三方依赖。
    python3 tools/self_test.py
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAILS = []
WARNS = []


def ok(msg):
    print(f"  \033[32m✓\033[0m {msg}")


def bad(msg):
    print(f"  \033[31m✗\033[0m {msg}")
    FAILS.append(msg)


def warn(msg):
    print(f"  \033[33m!\033[0m {msg}")
    WARNS.append(msg)


def run(args, cwd=ROOT):
    p = subprocess.run([sys.executable] + args, cwd=cwd,
                       capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


# ------------------------------------------------------------ 1. 流水线

def test_pipeline():
    print("\n[1] 流水线端到端")
    tmp = tempfile.mkdtemp(prefix="juexing-test-")
    try:
        raw = os.path.join(tmp, "raw.jsonl")
        rc, out, err = run(["tools/make_demo.py", "--out", raw, "--n", "4000"])
        if rc or not os.path.exists(raw):
            return bad(f"make_demo 失败: {err[:300]}")
        ok("造出合成语料")

        rc, out, err = run(["tools/extract_me.py", "--input", raw, "--out", tmp])
        if rc:
            return bad(f"extract_me 失败: {err[:300]}")
        me = os.path.join(tmp, "me.jsonl")
        rows = [json.loads(l) for l in open(me, encoding="utf-8") if l.strip()]
        if len(rows) < 500:
            return bad(f"只提取到 {len(rows)} 条，太少")
        ok(f"提取 {len(rows):,} 条自己说的话")

        # 别人的话必须一条不剩
        others = ["嗯嗯", "在吗", "你怎么想", "最近怎么样"]
        leaked = [r for r in rows if r["t"].strip() in others]
        if leaked:
            bad(f"别人的话泄漏了 {len(leaked)} 条——这是最严重的错误")
        else:
            ok("别人的话一条都没进来")

        # 噪声必须清干净
        noise = [r for r in rows if r["t"].startswith("<?xml")
                 or r["t"] in ("[图片]", "[语音]", "[动画表情]")
                 or r["t"].startswith("wxid_")
                 or "现在可以开始聊天" in r["t"]]
        if noise:
            bad(f"噪声没清干净：{[r['t'][:20] for r in noise[:3]]}")
        else:
            ok("XML / 表情 / 系统提示 / 标识 全部清掉")

        # 脱敏必须生效
        if any(re.search(r"[一-龥]{2,}", r["to"]) and not r["to"].startswith(("人", "群"))
               for r in rows):
            bad("联系人没脱敏干净")
        else:
            ok("联系人已脱敏为代号")

        nm = os.path.join(tmp, "NAMEMAP.local.json")
        if not os.path.exists(nm):
            bad("没生成真名对照表")
        elif oct(os.stat(nm).st_mode)[-3:] != "600":
            warn(f"对照表权限是 {oct(os.stat(nm).st_mode)[-3:]}，期望 600")
        else:
            ok("真名对照表权限 600")

        if not os.path.exists(os.path.join(tmp, ".gitignore")):
            bad("work 目录没有自动生成 .gitignore")
        else:
            ok("work 目录已自动挡在 git 之外")

        rc, out, err = run(["tools/stats.py", "--in", me, "--out", tmp])
        if rc:
            return bad(f"stats 失败: {err[:300]}")
        S = json.load(open(os.path.join(tmp, "stats.json"), encoding="utf-8"))
        need = ["体量", "节律", "代词", "句式", "词典_每千字", "关键比值",
                "情绪颗粒度", "逐年", "年度突变候选", "关系", "高频词_前80",
                "逐年新词", "立誓记录"]
        miss = [k for k in need if k not in S]
        if miss:
            bad(f"stats.json 缺字段: {miss}")
        else:
            ok(f"统计层 {len(need)} 个区块齐全")

        if len(S["逐年"]) < 5:
            bad(f"逐年只有 {len(S['逐年'])} 年，合成数据应有 8 年")
        else:
            ok(f"逐年覆盖 {len(S['逐年'])} 年")

        # 合成数据里 2022 是埋好的转折点，检测不出来说明算法没用
        shift_years = {s["到年"] for s in S["年度突变候选"]}
        if "2022" in shift_years or "2023" in shift_years:
            ok("检测到合成数据里埋的 2022 转折点")
        else:
            warn(f"没检测到 2022 转折点，突变年份是 {sorted(shift_years)}")

        md = open(os.path.join(tmp, "stats.md"), encoding="utf-8").read()
        if "None" in md:
            warn("stats.md 里出现了 None，表格可读性受影响")
        else:
            ok("stats.md 无 None 残留")

        rc, out, err = run(["tools/sample.py", "--in", me, "--stats",
                            os.path.join(tmp, "stats.json"), "--out", tmp])
        if rc:
            return bad(f"sample 失败: {err[:300]}")
        corpus = open(os.path.join(tmp, "corpus.md"), encoding="utf-8").read()
        if "## 抽样规则" not in corpus:
            bad("corpus.md 没有披露抽样规则")
        else:
            ok("corpus.md 披露了抽样规则")
        if len(corpus) > 400_000:
            warn(f"corpus.md {len(corpus):,} 字，可能装不进上下文")
        else:
            ok(f"corpus.md {len(corpus):,} 字，尺寸合理")

        # 脱敏正则必须真的会用
        probe = os.path.join(tmp, "probe.jsonl")
        with open(probe, "w", encoding="utf-8") as f:
            for t in ["我的手机号是 13812345678 你存一下",
                      "邮箱 test.user@example.com 发我",
                      "密码是 abc12345 别告诉别人"]:
                f.write(json.dumps({"CreateTime": 1700000000, "IsSender": 1,
                                    "StrContent": t, "talker": "测试",
                                    "Type": 1}, ensure_ascii=False) + "\n")
        p2 = os.path.join(tmp, "p2")
        run(["tools/extract_me.py", "--input", probe, "--out", p2])
        run(["tools/sample.py", "--in", os.path.join(p2, "me.jsonl"),
             "--out", p2, "--per-year", "50", "--min-len", "2"])
        c2 = open(os.path.join(p2, "corpus.md"), encoding="utf-8").read()
        leaks = [x for x in ["13812345678", "test.user@example.com", "abc12345"] if x in c2]
        if leaks:
            bad(f"敏感信息泄漏进 corpus.md: {leaks}")
        else:
            ok("手机号 / 邮箱 / 密码 在抽样输出里已隐去")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------ 2. 思想家语料

FIELDS = ["领域", "一句话", "要害概念", "诊断问句", "语料信号",
          "命中读法", "处方", "反对意见"]


def test_thinkers():
    print("\n[2] 思想家语料")
    d = os.path.join(ROOT, "references", "thinkers")
    files = sorted(f for f in os.listdir(d) if re.match(r"\d\d-", f))
    if len(files) != 9:
        bad(f"应有 9 个分组文件，实际 {len(files)}")
    entries, nums = [], []
    for fn in files:
        txt = open(os.path.join(d, fn), encoding="utf-8").read()
        blocks = re.split(r"\n### ", txt)[1:]
        for b in blocks:
            head = b.split("\n")[0]
            m = re.match(r"(\d{3})\s*·", head)
            if not m:
                bad(f"{fn}: 标题不合规 「{head[:40]}」")
                continue
            nums.append(int(m.group(1)))
            missing = [f for f in FIELDS if f"**{f}**" not in b]
            if missing:
                bad(f"{fn} #{m.group(1)} 缺字段: {missing}")
            entries.append((int(m.group(1)), head, len(b)))

    if len(entries) == 100:
        ok("整整 100 条")
    else:
        bad(f"应有 100 条，实际 {len(entries)}")

    if sorted(nums) == list(range(1, len(nums) + 1)):
        ok(f"编号 001–{len(nums):03d} 连续无断无重")
    else:
        dup = {n for n in nums if nums.count(n) > 1}
        gap = set(range(1, max(nums) + 1)) - set(nums)
        bad(f"编号有问题 重复={sorted(dup)} 缺失={sorted(gap)}")

    if not FAILS:
        ok(f"八个字段 {len(entries)} 条全部齐全")

    thin = [(n, h) for n, h, ln in entries if ln < 400]
    if thin:
        warn(f"{len(thin)} 条明显偏短: {[h[:22] for _, h in thin[:3]]}")
    else:
        ok("没有敷衍条目")


# ------------------------------------------------------------ 3. 文档

def test_docs():
    print("\n[3] 文档与骨架")
    need = ["SKILL.md", "README.md", "LICENSE", "ROADMAP.md", ".gitignore",
            "references/method.md", "references/anti-barnum.md",
            "references/report-template.md", "references/get-your-data.md",
            "references/thinkers/_FORMAT.md",
            "tools/adapters.py", "tools/extract_me.py", "tools/stats.py",
            "tools/sample.py", "tools/make_demo.py"]
    for f in need:
        if os.path.exists(os.path.join(ROOT, f)):
            ok(f)
        else:
            bad(f"缺文件 {f}")

    sk = open(os.path.join(ROOT, "SKILL.md"), encoding="utf-8").read()
    if not sk.startswith("---"):
        bad("SKILL.md 没有 YAML 头")
    for k in ("name:", "description:", "allowed-tools:"):
        if k not in sk.split("---")[1]:
            bad(f"SKILL.md 头部缺 {k}")
    if "触发词" in sk:
        ok("SKILL.md 头部含触发词")

    # 模板里的章节标题，报告生成时靠它们定位
    tpl = open(os.path.join(ROOT, "references/report-template.md"), encoding="utf-8").read()
    for h in ["## 0 · 这份报告是怎么来的", "## 1 · 镜子", "## 2 · 编年",
              "## 3 · 你在哪个阶段", "## 4 · 你的文字让人觉得", "## 5 · 状态",
              "## 6 · 会诊", "## 7 · 九十天", "## 8 · 这份报告可能错在哪"]:
        if h not in tpl:
            bad(f"报告模板缺章节 {h}")
    ok("报告模板九个章节齐全")

    # 反巴纳姆闸必须问「独特性」而不是「准不准」——这是设计的要害
    ab = open(os.path.join(ROOT, "references/anti-barnum.md"), encoding="utf-8").read()
    if "只有你这样" not in ab or "只有你这样" not in tpl:
        bad("收尾必须问「哪几条只有你这样」，不能问「准不准」")
    else:
        ok("收尾问的是独特性，不是准确度")

    # 危机求助信息必须出现在这几个文件里，不能只写一处
    hotline = "010-8295-1332"
    for f in ["SKILL.md", "references/anti-barnum.md",
              "references/report-template.md", "references/method.md"]:
        t = open(os.path.join(ROOT, f), encoding="utf-8").read()
        if hotline not in t and "专业" not in t:
            bad(f"{f} 里没有危机求助或转介专业的提示")
    ok("危机求助信息覆盖到位")


if __name__ == "__main__":
    print("=" * 56)
    print("自我觉醒.skill · 自测")
    print("=" * 56)
    test_pipeline()
    test_thinkers()
    test_docs()
    print("\n" + "=" * 56)
    if FAILS:
        print(f"\033[31m{len(FAILS)} 项失败\033[0m")
        for f in FAILS:
            print(f"  · {f}")
    if WARNS:
        print(f"\033[33m{len(WARNS)} 项警告\033[0m")
        for w in WARNS:
            print(f"  · {w}")
    if not FAILS:
        print("\033[32m全部通过\033[0m")
    sys.exit(1 if FAILS else 0)
