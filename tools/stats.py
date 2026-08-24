#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stats.py —— 把「我说过的话」算成一堆没法抵赖的数字。

为什么要有这一步：
    直接把聊天记录丢给模型，它会回你一段「你内心敏感、渴望被理解、外表坚强」。
    这种话对谁都成立，因此对谁都没用。
    这个脚本先在本地把可数的东西数出来——代词比例、义务词对意愿词的比值、深夜消息占比、
    对不同人的说话方式差异、逐年的变化曲线。模型后面下的每一个判断，都必须落在这些数字上。
    数字不保证结论正确，但它保证结论**可以被推翻**。这是和算命的唯一区别。

零第三方依赖。有 jieba 就用，没有就退化到基于词典与 n-gram 的统计，不影响主要指标。

用法：
    python3 stats.py --in ./work/me.jsonl --out ./work
产出：
    stats.json   全部指标，机器读
    stats.md     人和模型都能读的摘要，是后续分析的唯一事实底座
"""

import argparse
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict

# ============================================================ 词典
# 说明：这些词典是「信号」不是「诊断」。命中率高只说明值得去看语料，不说明任何结论。
# 每个词典都保守：宁可漏，不可为了凑数把中性词算进来。

LEX = {
    # —— 自我决定论：我想做 vs 我必须做 ——
    "义务": ["应该", "必须", "不得不", "只能", "被迫", "没办法", "没辙", "逼着",
             "要不然", "不然的话", "硬着头皮", "不敢不", "轮不到我", "身不由己",
             "没得选", "别无选择", "只好", "迫于"],
    "意愿": ["我想", "我要", "我希望", "我打算", "我准备", "我决定", "我喜欢",
             "我愿意", "我期待", "我打定", "我就是想", "我更想", "我宁愿"],

    # —— 确定性 ——
    "模糊": ["可能", "也许", "大概", "应该是", "我觉得", "好像", "似乎", "差不多",
             "貌似", "或许", "说不定", "大约", "有点", "多少有点", "算是", "感觉"],
    "确定": ["一定", "肯定", "必然", "毫无疑问", "确定", "我确信", "绝对", "就是"],

    # —— 姿态 ——
    "道歉": ["对不起", "不好意思", "抱歉", "是我的错", "我的锅", "打扰了", "麻烦你了",
             "见谅", "我错了", "怪我"],
    "感谢": ["谢谢", "感谢", "辛苦了", "多谢", "麻烦您", "太感谢"],
    "自贬": ["我不行", "我不配", "我太差", "我很笨", "我没用", "我真菜", "我废物",
             "我做不到", "我不够", "我这种人", "像我这样", "我又搞砸", "我果然"],
    "认输": ["算了", "随便", "无所谓", "都行", "看你吧", "你决定", "爱咋咋", "摆烂",
             "躺平", "不想争", "懒得说", "没意思"],

    # —— 情绪（负面按类别分开，用于算情绪颗粒度）——
    "疲惫": ["累", "疲惫", "熬不住", "撑不住", "透支", "耗尽", "没劲", "倦"],
    "焦虑": ["焦虑", "紧张", "慌", "担心", "害怕", "怕", "不安", "心慌", "压力", "怕来不及"],
    "抑郁": ["抑郁", "emo", "低落", "提不起劲", "空", "麻木", "没意义", "活着没意思", "绝望"],
    "愤怒": ["生气", "火大", "气死", "恶心", "烦死", "受不了", "凭什么", "离谱", "无语"],
    "悲伤": ["难过", "难受", "想哭", "哭", "心疼", "委屈", "失落", "遗憾", "舍不得"],
    "孤独": ["孤独", "一个人", "没人", "孤单", "没人懂", "没人陪", "自己扛"],
    "羞耻": ["丢人", "尴尬", "没脸", "羞", "抬不起头", "自卑"],
    "正面": ["开心", "高兴", "爽", "喜欢", "期待", "满足", "幸福", "有意思", "值得",
             "舒服", "过瘾", "感动", "踏实", "安心", "自在", "松了口气", "太好了"],

    # —— 时间取向 ——
    "过去": ["以前", "当初", "那时候", "曾经", "小时候", "后悔", "早知道", "本来",
             "原来", "过去", "从前", "要是当时"],
    "未来": ["以后", "将来", "打算", "计划", "等我", "明年", "下次", "回头", "接下来",
             "总有一天", "迟早", "到时候"],
    "当下": ["现在", "今天", "正在", "此刻", "眼下", "目前", "刚刚", "马上"],

    # —— 关系姿态（戈特曼四骑士的文字版，粗略近似）——
    "批评": ["你总是", "你从来", "你就是", "你怎么老", "你根本", "你永远"],
    "蔑视": ["呵呵", "就这", "你也配", "笑死", "幼稚", "你懂什么", "无知"],
    "防御": ["不是我", "又不是我的错", "我哪知道", "关我什么事", "你还不是", "我又没"],
    "筑墙": ["不想说了", "别说了", "随你", "没什么好说", "算了不聊"],

    # —— 立誓与延宕 ——
    "立誓": ["从明天开始", "从今天起", "我一定要", "我发誓", "这次一定", "我要开始",
             "从下周", "从下个月", "痛定思痛", "重新开始"],
    "延宕": ["等我", "等到", "忙完这阵", "等有空", "过阵子", "再说吧", "以后再",
             "改天", "有机会", "等稳定了"],

    # —— 求助与边界 ——
    "求助": ["能不能帮我", "求你", "帮个忙", "拜托", "可以吗", "方便吗"],
    # 注意：这里刻意不放「我不」这种两字前缀——它会把「我不该那么说」「我不知道」
    # 全部误判成拒绝。宁可漏检，不可污染。
    "拒绝": ["我拒绝", "我做不了", "我不做", "我不去", "我不干", "我不参加", "我不同意",
             "我不接", "我退出", "恕我", "我没空", "抽不开身", "这个不归我", "我不愿意"],
    "讨好": ["都听你的", "你说了算", "我配合", "你开心就好", "我无所谓的", "随你安排",
             "怎么方便怎么来"],

    # —— 存在类（海德格尔的『大家都这样』、萨特的自欺）——
    "从众": ["大家都", "别人都", "人家都", "都这样", "正常人", "谁不是", "都得",
             "这个年纪", "到了年龄"],
    "自欺": ["我就是这样的人", "我这人就", "我天生", "改不了", "性格如此", "没办法我",
             "我控制不住", "本性难移"],
}

PRONOUNS = {
    "我": ["我", "我的", "我们"],   # 单独处理，见下
}

STOPWORDS = set("""的 了 是 在 我 有 和 就 不 人 都 一 一个 上 也 很 到 说 要 去 你 会 着
没有 看 好 自己 这 那 他 她 它 们 什么 怎么 但是 因为 所以 如果 可以 这个 那个 还是 现在
知道 觉得 时候 事情 问题 感觉 就是 一下 一样 这样 那样 之后 已经 还有 或者 而且 然后 其实
可能 应该 需要 还有 真的 特别 非常 比较 有点 这么 那么 一直 已经 曾经 刚才 今天 明天 昨天
你们 他们 咱们 大家 东西 地方 时间 电话 微信 消息 哈哈 哈哈哈 嗯嗯 好的 好呀 行吧 ok OK
是的 对的 没事 不用 谢谢 一起 可能 应该""".split())


# ============================================================ 工具函数

def load(path):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                rows.append(json.loads(ln))
    return rows


def per_k(count, total_chars):
    """每千字出现次数。用比率而不是绝对数，跨年才可比。"""
    return round(count / total_chars * 1000, 2) if total_chars else 0.0


def ratio(a, b):
    """a÷b。分母为 0 时不返回 None——那样表格里读不出信息。
    分母为 0 而分子不为 0，本身就是一个强信号（「一次都没说过我想」），要说出来。"""
    if b:
        return round(a / b, 2)
    if a:
        return "∞"          # 分子有、分母零：极端值，比任何数字都值得看
    return None             # 两边都是零：真的没数据


def count_lex(texts_joined, words):
    return sum(texts_joined.count(w) for w in words)


def try_jieba():
    try:
        import jieba  # noqa
        return jieba
    except ImportError:
        return None


def tokenize(text, jb):
    if jb:
        return [w for w in jb.cut(text) if len(w) >= 2 and re.search(r"[一-龥a-zA-Z]", w)]
    # 无 jieba：取 2~3 字中文片段做近似
    out = []
    for seg in re.findall(r"[一-龥]{2,}", text):
        for n in (2, 3):
            for i in range(len(seg) - n + 1):
                out.append(seg[i:i + n])
    out += re.findall(r"[a-zA-Z]{3,}", text)
    return out


# ============================================================ 主体

def analyze(rows, jb=None):
    S = {}
    total = len(rows)
    all_text = "\n".join(r["t"] for r in rows)
    total_chars = sum(r["n"] for r in rows)

    # ---------- 1. 体量与节律 ----------
    days = sorted({r["ts"][:10] for r in rows})
    by_year = defaultdict(list)
    for r in rows:
        by_year[r["y"]].append(r)
    hours = Counter(r["hour"] for r in rows)
    wds = Counter(r["wd"] for r in rows)

    # 最长沉默
    from datetime import date
    dl = [date(*map(int, d.split("-"))) for d in days]
    gaps = [((dl[i + 1] - dl[i]).days, days[i], days[i + 1]) for i in range(len(dl) - 1)]
    gaps.sort(reverse=True)

    S["体量"] = {
        "消息条数": total,
        "总字数": total_chars,
        "起止": [rows[0]["ts"][:10], rows[-1]["ts"][:10]] if rows else [],
        "有说话的天数": len(days),
        "跨度天数": (dl[-1] - dl[0]).days + 1 if len(dl) > 1 else 1,
        "平均每条字数": round(total_chars / total, 1) if total else 0,
        "长消息占比_超50字": round(sum(1 for r in rows if r["n"] > 50) / total, 3) if total else 0,
        "一句话消息占比_不超10字": round(sum(1 for r in rows if r["n"] <= 10) / total, 3) if total else 0,
        "最长沉默": [{"天数": g[0], "从": g[1], "到": g[2]} for g in gaps[:5]],
    }

    S["节律"] = {
        "按小时": {str(h): hours.get(h, 0) for h in range(24)},
        "深夜占比_0到5点": round(sum(hours.get(h, 0) for h in range(0, 6)) / total, 3) if total else 0,
        "凌晨占比_1到4点": round(sum(hours.get(h, 0) for h in range(1, 5)) / total, 3) if total else 0,
        "工作时段占比_9到18点": round(sum(hours.get(h, 0) for h in range(9, 19)) / total, 3) if total else 0,
        "按星期": {"周一二三四五六日"[i]: wds.get(i, 0) for i in range(7)},
        "周末占比": round((wds.get(5, 0) + wds.get(6, 0)) / total, 3) if total else 0,
    }

    # ---------- 2. 代词 ----------
    # 「我们」会被「我」的计数吃掉，先算复数再从单数里减掉
    n_women = all_text.count("我们") + all_text.count("咱们")
    n_wo_all = all_text.count("我")
    n_wo = n_wo_all - all_text.count("我们")
    n_ni = all_text.count("你") + all_text.count("您")
    n_ta = all_text.count("他") + all_text.count("她") + all_text.count("它")

    S["代词"] = {
        "我_每千字": per_k(n_wo, total_chars),
        "我们_每千字": per_k(n_women, total_chars),
        "你_每千字": per_k(n_ni, total_chars),
        "他她_每千字": per_k(n_ta, total_chars),
        "我对我们比": round(n_wo / n_women, 2) if n_women else None,
        "我对你比": round(n_wo / n_ni, 2) if n_ni else None,
        "含我的消息占比": round(sum(1 for r in rows if "我" in r["t"]) / total, 3) if total else 0,
    }

    # ---------- 3. 句式 ----------
    q = sum(1 for r in rows if re.search(r"[?？]", r["t"])
            or re.search(r"(吗|呢|吧)\s*$", r["t"]))
    ex = all_text.count("!") + all_text.count("！")
    ell = len(re.findall(r"(?:\.{3,}|。{2,}|…+)", all_text))

    S["句式"] = {
        "疑问句占比": round(q / total, 3) if total else 0,
        "感叹号_每千字": per_k(ex, total_chars),
        "省略号_每千字": per_k(ell, total_chars),
        "但是转折_每千字": per_k(count_lex(all_text, ["但是", "可是", "不过", "然而", "只是"]), total_chars),
        "反问_每千字": per_k(count_lex(all_text, ["难道", "凭什么", "有什么用", "又能怎样", "不然呢"]), total_chars),
    }

    # ---------- 4. 词典命中（全局 + 逐年）----------
    def lexblock(text, chars):
        return {k: per_k(count_lex(text, v), chars) for k, v in LEX.items()}

    S["词典_每千字"] = lexblock(all_text, total_chars)

    ob = S["词典_每千字"]["义务"]
    wi = S["词典_每千字"]["意愿"]
    S["关键比值"] = {
        "义务对意愿": ratio(ob, wi),
        "模糊对确定": ratio(S["词典_每千字"]["模糊"], S["词典_每千字"]["确定"]),
        "正面对负面": None,  # 下面填
        "立誓对延宕": ratio(S["词典_每千字"]["立誓"], S["词典_每千字"]["延宕"]),
    }
    neg_keys = ["疲惫", "焦虑", "抑郁", "愤怒", "悲伤", "孤独", "羞耻"]
    neg_sum = sum(S["词典_每千字"][k] for k in neg_keys)
    S["关键比值"]["正面对负面"] = ratio(S["词典_每千字"]["正面"], neg_sum)

    # 情绪颗粒度（巴瑞特）：用到了多少个不同的情绪词
    used_emotion_words = set()
    for k in neg_keys + ["正面"]:
        for w in LEX[k]:
            if w in all_text:
                used_emotion_words.add(w)
    all_emotion_words = sum(len(LEX[k]) for k in neg_keys + ["正面"])
    S["情绪颗粒度"] = {
        "用过的情绪词种类": len(used_emotion_words),
        "词库总数": all_emotion_words,
        "覆盖率": round(len(used_emotion_words) / all_emotion_words, 3),
        "主导负面类别": max(neg_keys, key=lambda k: S["词典_每千字"][k]) if neg_sum else None,
        "各负面类别": {k: S["词典_每千字"][k] for k in neg_keys},
    }

    # ---------- 5. 逐年 ----------
    yearly = {}
    for y in sorted(by_year):
        yr = by_year[y]
        yt = "\n".join(r["t"] for r in yr)
        yc = sum(r["n"] for r in yr)
        yl = lexblock(yt, yc)
        ynw = yt.count("我") - yt.count("我们")
        yneg = sum(yl[k] for k in neg_keys)
        yearly[str(y)] = {
            "条数": len(yr),
            "字数": yc,
            "平均长度": round(yc / len(yr), 1),
            "深夜占比": round(sum(1 for r in yr if r["hour"] < 6) / len(yr), 3),
            "我_每千字": per_k(ynw, yc),
            "我们_每千字": per_k(yt.count("我们") + yt.count("咱们"), yc),
            "义务": yl["义务"], "意愿": yl["意愿"],
            "义务对意愿": ratio(yl["义务"], yl["意愿"]),
            "负面总和": round(yneg, 2), "正面": yl["正面"],
            "正面对负面": ratio(yl["正面"], yneg),
            "自贬": yl["自贬"], "认输": yl["认输"], "道歉": yl["道歉"],
            "从众": yl["从众"], "自欺": yl["自欺"],
            "延宕": yl["延宕"], "立誓": yl["立誓"],
            "过去": yl["过去"], "未来": yl["未来"], "当下": yl["当下"],
            "主导负面": max(neg_keys, key=lambda k: yl[k]) if yneg else None,
            "联系人数": len({r["to"] for r in yr}),
        }
    S["逐年"] = yearly

    # 逐年变化里最剧烈的那几项（自动找转折点候选）
    ys = sorted(yearly)
    shifts = []
    if len(ys) >= 2:
        watch = ["平均长度", "深夜占比", "我_每千字", "义务对意愿", "正面对负面",
                 "自贬", "认输", "延宕", "从众", "联系人数", "条数"]
        for key in watch:
            for i in range(len(ys) - 1):
                a, b = yearly[ys[i]].get(key), yearly[ys[i + 1]].get(key)
                if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
                    continue          # "∞" 或 None 不参与变化率计算
                if a == 0:
                    continue
                chg = (b - a) / abs(a)
                if abs(chg) >= 0.4:
                    shifts.append({"指标": key, "从年": ys[i], "到年": ys[i + 1],
                                   "从": a, "到": b, "变化": round(chg, 2)})
    shifts.sort(key=lambda d: -abs(d["变化"]))
    S["年度突变候选"] = shifts[:25]

    # ---------- 6. 关系层：对不同人说话方式的差异 ----------
    by_to = defaultdict(list)
    for r in rows:
        by_to[r["to"]].append(r)
    contacts = []
    for code, rs in by_to.items():
        if len(rs) < 30:      # 样本太小的不做语言学比较，否则全是噪声
            continue
        t = "\n".join(x["t"] for x in rs)
        c = sum(x["n"] for x in rs)
        l = lexblock(t, c)
        contacts.append({
            "代号": code, "群": rs[0]["grp"], "条数": len(rs), "字数": c,
            "平均长度": round(c / len(rs), 1),
            "首次": rs[0]["ts"][:10], "末次": rs[-1]["ts"][:10],
            "活跃年份": sorted({x["y"] for x in rs}),
            "我_每千字": per_k(t.count("我") - t.count("我们"), c),
            "深夜占比": round(sum(1 for x in rs if x["hour"] < 6) / len(rs), 3),
            "疑问句占比": round(sum(1 for x in rs if re.search(r"[?？]|(吗|呢|吧)\s*$", x["t"])) / len(rs), 3),
            "道歉": l["道歉"], "讨好": l["讨好"], "拒绝": l["拒绝"],
            "义务": l["义务"], "意愿": l["意愿"], "自贬": l["自贬"],
            "正面": l["正面"], "负面": round(sum(l[k] for k in neg_keys), 2),
            "批评": l["批评"], "蔑视": l["蔑视"], "防御": l["防御"], "筑墙": l["筑墙"],
        })
    contacts.sort(key=lambda d: -d["条数"])
    S["关系"] = {
        "联系人总数": len(by_to),
        "群数": sum(1 for rs in by_to.values() if rs[0]["grp"]),
        "达到统计门槛的": len(contacts),
        "前20": contacts[:20],
    }

    # 消失的人 / 新出现的人
    if len(ys) >= 2:
        last_y, prev_y = int(ys[-1]), int(ys[-2])
        act = defaultdict(set)
        for r in rows:
            act[r["to"]].add(r["y"])
        gone = [{"代号": c, "最后活跃": max(v), "总条数": len(by_to[c])}
                for c, v in act.items()
                if max(v) < last_y and len(by_to[c]) >= 50]
        gone.sort(key=lambda d: -d["总条数"])
        newp = [{"代号": c, "首次出现": min(v), "总条数": len(by_to[c])}
                for c, v in act.items()
                if min(v) >= prev_y and len(by_to[c]) >= 50]
        newp.sort(key=lambda d: -d["总条数"])
        S["关系"]["淡出的人_曾经高频后来归零"] = gone[:15]
        S["关系"]["近两年才出现的人"] = newp[:15]

    # 「只对某些人说的话」：某个代号上某类词显著高于自己的整体基线
    outliers = []
    for c in contacts[:20]:
        for k in ["道歉", "讨好", "自贬", "义务", "负面", "拒绝", "意愿", "正面"]:
            base = (S["词典_每千字"].get(k) if k not in ("负面",) else neg_sum) or 0
            v = c[k]
            if base > 0.05 and v / base >= 2.0 and v >= 0.3:
                outliers.append({"代号": c["代号"], "维度": k, "他那里": v,
                                 "我的平均": round(base, 2), "倍数": round(v / base, 1)})
    outliers.sort(key=lambda d: -d["倍数"])
    S["关系"]["人格分裂点_对某人格外如何"] = outliers[:20]

    # ---------- 7. 词汇指纹 ----------
    toks = Counter()
    for r in rows:
        for w in tokenize(r["t"], jb):
            if w not in STOPWORDS and len(w) >= 2:
                toks[w] += 1
    S["高频词_前80"] = [{"词": w, "次": n} for w, n in toks.most_common(80)]

    # 逐年的「新词」与「消失的词」——一个人什么时候开始说某个词，是最硬的转折点线索
    year_toks = {}
    for y in sorted(by_year):
        c = Counter()
        for r in by_year[y]:
            for w in tokenize(r["t"], jb):
                if w not in STOPWORDS and len(w) >= 2:
                    c[w] += 1
        year_toks[str(y)] = c
    newwords = {}
    for i in range(1, len(ys)):
        prev = set()
        for j in range(i):
            prev |= {w for w, n in year_toks[ys[j]].items() if n >= 3}
        cur = year_toks[ys[i]]
        cand = [(w, n) for w, n in cur.items() if n >= 8 and w not in prev]
        cand.sort(key=lambda x: -x[1])
        newwords[ys[i]] = [{"词": w, "次": n} for w, n in cand[:15]]
    S["逐年新词"] = newwords

    faded = {}
    for i in range(len(ys) - 1):
        cur = {w: n for w, n in year_toks[ys[i]].items() if n >= 10}
        later = Counter()
        for j in range(i + 1, len(ys)):
            later += year_toks[ys[j]]
        cand = [(w, n) for w, n in cur.items() if later.get(w, 0) <= max(1, n * 0.1)]
        cand.sort(key=lambda x: -x[1])
        if cand:
            faded[ys[i]] = [{"词": w, "当年次数": n} for w, n in cand[:10]]
    S["从此不再说的词"] = faded

    # ---------- 8. 立誓追踪 ----------
    vows = []
    for r in rows:
        if any(w in r["t"] for w in LEX["立誓"]):
            vows.append({"时间": r["ts"][:10], "对象": r["to"], "原话": r["t"][:120]})
    S["立誓记录"] = {"总数": len(vows), "样本": vows[:40]}

    # ---------- 9. 最长的话 ----------
    longest = sorted(rows, key=lambda r: -r["n"])[:15]
    S["最长的消息"] = [{"时间": r["ts"][:10], "对象": r["to"], "字数": r["n"],
                       "开头": r["t"][:80]} for r in longest]

    return S


# ============================================================ 摘要渲染

def render_md(S, jb_on):
    L = []
    A = L.append
    b = S["体量"]
    A("# 数字层 · 你说过的话，数出来是这样")
    A("")
    A("> 这一页只有数字，没有解释。任何解释都必须回到这里，不能凭空来。")
    A(f"> 分词{'已启用 jieba' if jb_on else '未装 jieba，词频用 n-gram 近似（不影响词典类指标）'}。")
    A("")
    A("## 一、体量")
    A("")
    A(f"- 我说过 **{b['消息条数']:,} 条**，共 **{b['总字数']:,} 字**")
    A(f"- 时间跨度 {b['起止'][0]} → {b['起止'][1]}，共 {b['跨度天数']:,} 天，其中 {b['有说话的天数']:,} 天有记录")
    A(f"- 平均每条 {b['平均每条字数']} 字；超过 50 字的长消息占 {b['长消息占比_超50字']:.1%}；"
      f"不超过 10 字的短消息占 {b['一句话消息占比_不超10字']:.1%}")
    if b["最长沉默"]:
        g = b["最长沉默"][0]
        A(f"- 最长的一次沉默 **{g['天数']} 天**（{g['从']} → {g['到']}）")
    A("")

    r = S["节律"]
    A("## 二、什么时候说话")
    A("")
    A(f"- 深夜（0–5 点）占 **{r['深夜占比_0到5点']:.1%}**，其中凌晨 1–4 点占 {r['凌晨占比_1到4点']:.1%}")
    A(f"- 白天工作时段（9–18 点）占 {r['工作时段占比_9到18点']:.1%}；周末占 {r['周末占比']:.1%}")
    peak = max(r["按小时"], key=lambda k: r["按小时"][k])
    A(f"- 话最多的一个小时是 **{peak} 点**")
    A("")

    p = S["代词"]
    A("## 三、代词")
    A("")
    A("| 指标 | 值 |")
    A("|---|---|")
    A(f"| 「我」每千字 | {p['我_每千字']} |")
    A(f"| 「我们」每千字 | {p['我们_每千字']} |")
    A(f"| 「你」每千字 | {p['你_每千字']} |")
    A(f"| 「他/她」每千字 | {p['他她_每千字']} |")
    A(f"| 我 ÷ 我们 | {p['我对我们比']} |")
    A(f"| 我 ÷ 你 | {p['我对你比']} |")
    A(f"| 含「我」的消息占比 | {p['含我的消息占比']:.1%} |")
    A("")

    k = S["关键比值"]
    A("## 四、四个关键比值")
    A("")
    A("| 比值 | 值 | 怎么读 |")
    A("|---|---|---|")
    A(f"| 义务词 ÷ 意愿词 | **{k['义务对意愿']}** | 大于 1 说明说「必须」比说「我想」多 |")
    A(f"| 模糊词 ÷ 确定词 | {k['模糊对确定']} | 高说明习惯给自己留退路 |")
    A(f"| 正面情绪 ÷ 负面情绪 | **{k['正面对负面']}** | 只做纵向自比，不和别人比 |")
    A(f"| 立誓 ÷ 延宕 | {k['立誓对延宕']} | 都高 = 反复起誓反复推迟 |")
    A("")

    g = S["情绪颗粒度"]
    A("## 五、情绪")
    A("")
    A(f"- 情绪词种类 **{g['用过的情绪词种类']} / {g['词库总数']}**（覆盖率 {g['覆盖率']:.1%}）"
      f"——能用多少种词说难受，决定你能分辨多少种难受")
    A(f"- 主导的负面类别：**{g['主导负面类别']}**")
    A("")
    A("| 类别 | 每千字 |")
    A("|---|---|")
    for kk, vv in sorted(g["各负面类别"].items(), key=lambda x: -x[1]):
        A(f"| {kk} | {vv} |")
    A("")

    A("## 六、其他词典命中（每千字）")
    A("")
    A("| 类别 | 值 | 类别 | 值 |")
    A("|---|---|---|---|")
    show = ["道歉", "感谢", "自贬", "认输", "讨好", "拒绝", "求助",
            "从众", "自欺", "延宕", "立誓", "过去", "未来", "当下",
            "批评", "蔑视", "防御", "筑墙"]
    d = S["词典_每千字"]
    for i in range(0, len(show), 2):
        a1 = show[i]
        a2 = show[i + 1] if i + 1 < len(show) else ""
        A(f"| {a1} | {d[a1]} | {a2} | {d.get(a2, '')} |")
    A("")

    A("## 七、逐年")
    A("")
    A("| 年 | 条数 | 均长 | 深夜 | 我/千字 | 义务÷意愿 | 正÷负 | 自贬 | 认输 | 延宕 | 从众 | 主导负面 | 联系人 |")
    A("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for y, v in S["逐年"].items():
        A(f"| {y} | {v['条数']:,} | {v['平均长度']} | {v['深夜占比']:.0%} | {v['我_每千字']} | "
          f"{v['义务对意愿']} | {v['正面对负面']} | {v['自贬']} | {v['认输']} | {v['延宕']} | "
          f"{v['从众']} | {v['主导负面'] or '—'} | {v['联系人数']} |")
    A("")

    if S["年度突变候选"]:
        A("### 变化最剧烈的指标（转折点候选，仅供追查，不是结论）")
        A("")
        A("| 指标 | 年份 | 从 → 到 | 变化 |")
        A("|---|---|---|---|")
        for s in S["年度突变候选"][:12]:
            A(f"| {s['指标']} | {s['从年']}→{s['到年']} | {s['从']} → {s['到']} | {s['变化']:+.0%} |")
        A("")

    rel = S["关系"]
    A("## 八、关系")
    A("")
    A(f"- 一共对 **{rel['联系人总数']}** 个会话说过话（其中群 {rel['群数']} 个），"
      f"其中 {rel['达到统计门槛的']} 个消息量足够做语言比较（≥30 条）")
    A("")
    A("### 说得最多的人（脱敏代号）")
    A("")
    A("| 代号 | 群 | 条数 | 均长 | 我/千字 | 疑问 | 深夜 | 道歉 | 讨好 | 拒绝 | 义务 | 意愿 | 正面 | 负面 | 活跃年 |")
    A("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for c in rel["前20"][:15]:
        A(f"| {c['代号']} | {'是' if c['群'] else ''} | {c['条数']:,} | {c['平均长度']} | {c['我_每千字']} | "
          f"{c['疑问句占比']:.0%} | {c['深夜占比']:.0%} | {c['道歉']} | {c['讨好']} | {c['拒绝']} | "
          f"{c['义务']} | {c['意愿']} | {c['正面']} | {c['负面']} | "
          f"{c['活跃年份'][0]}–{c['活跃年份'][-1]} |")
    A("")

    if rel.get("人格分裂点_对某人格外如何"):
        A("### 你在谁面前变形最厉害")
        A("")
        A("> 同一个人，对不同的人说话方式差多少倍。这一栏自带对照组，是全篇最硬的证据。")
        A("")
        A("| 代号 | 维度 | 对他 | 你的平均 | 倍数 |")
        A("|---|---|---|---|---|")
        for o in rel["人格分裂点_对某人格外如何"][:12]:
            A(f"| {o['代号']} | {o['维度']} | {o['他那里']} | {o['我的平均']} | {o['倍数']}× |")
        A("")

    if rel.get("淡出的人_曾经高频后来归零"):
        A("### 淡出的人（曾经说过很多话，后来归零）")
        A("")
        A(" · ".join(f"{x['代号']}（{x['总条数']}条，止于{x['最后活跃']}）"
                     for x in rel["淡出的人_曾经高频后来归零"][:10]))
        A("")
    if rel.get("近两年才出现的人"):
        A("### 新出现的人")
        A("")
        A(" · ".join(f"{x['代号']}（{x['总条数']}条，始于{x['首次出现']}）"
                     for x in rel["近两年才出现的人"][:10]))
        A("")

    A("## 九、词汇指纹")
    A("")
    A("**高频词前 40**：" + " · ".join(f"{x['词']}({x['次']})" for x in S["高频词_前80"][:40]))
    A("")
    if S["逐年新词"]:
        A("**每年第一次开始说的词**（强转折点线索）")
        A("")
        for y, ws in S["逐年新词"].items():
            if ws:
                A(f"- **{y}**：" + " · ".join(f"{w['词']}({w['次']})" for w in ws[:10]))
        A("")
    if S["从此不再说的词"]:
        A("**说过之后再也不说的词**")
        A("")
        for y, ws in S["从此不再说的词"].items():
            if ws:
                A(f"- **{y} 之后消失**：" + " · ".join(f"{w['词']}({w['当年次数']})" for w in ws[:8]))
        A("")

    v = S["立誓记录"]
    A("## 十、你对自己许过的愿")
    A("")
    A(f"共检出 **{v['总数']}** 次立誓类表达（「从明天开始」「这次一定」「我要开始」…）。")
    if v["样本"]:
        A("")
        for x in v["样本"][:12]:
            A(f"- `{x['时间']}` → {x['对象']}：{x['原话']}")
    A("")

    A("---")
    A("")
    A("**这一页的用法**：后面每一句关于「你是什么样的人」的判断，都要能指回上面某一行数字，"
      "或者指回原话。指不回去的，删掉。")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="把「我说过的话」算成数字")
    ap.add_argument("--in", dest="inp", default="./work/me.jsonl")
    ap.add_argument("--out", default="./work")
    args = ap.parse_args()

    if not os.path.exists(args.inp):
        print(f"[×] 找不到 {args.inp}，先跑 extract_me.py", file=sys.stderr)
        return 2

    rows = load(args.inp)
    if len(rows) < 50:
        print(f"[!] 只有 {len(rows)} 条，样本太小，统计结果不可信。"
              f"建议至少 1000 条以上再看结论。", file=sys.stderr)
    if not rows:
        return 1

    jb = try_jieba()
    if jb:
        try:
            jb.setLogLevel(60)
        except Exception:
            pass

    S = analyze(rows, jb)
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "stats.json"), "w", encoding="utf-8") as f:
        json.dump(S, f, ensure_ascii=False, indent=2)
    md = render_md(S, bool(jb))
    with open(os.path.join(args.out, "stats.md"), "w", encoding="utf-8") as f:
        f.write(md + "\n")

    print(f"[✓] {os.path.join(args.out, 'stats.json')}")
    print(f"[✓] {os.path.join(args.out, 'stats.md')}  ← 这份给模型读")
    print()
    print(md[:1400])
    print("\n……（完整内容见 stats.md）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
