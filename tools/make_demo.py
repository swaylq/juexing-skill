#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_demo.py —— 造一份合成语料，用来自测流水线，也用来当公开示例。

里面这个「人」是编的：一个 2019 年入职、2022 年经历某个转折、
之后说话变短变晚、义务词上升的虚构角色。**没有任何真人数据。**
造他的目的是：让别人不用交出自己的聊天记录，就能看到这个 skill 的输出长什么样。

用法：
    python3 make_demo.py --out ./work-demo/raw.jsonl
"""

import argparse
import json
import os
import random
from datetime import datetime, timedelta

R = random.Random(42)

CONTACTS = [
    ("老板张", False, (2019, 2026), "work"),
    ("同事小李", False, (2019, 2026), "work"),
    ("项目群", True, (2019, 2026), "work"),
    ("妈", False, (2019, 2026), "family"),
    ("大学室友", False, (2019, 2023), "friend"),
    ("阿哲", False, (2019, 2026), "friend"),
    ("林", False, (2020, 2022), "partner"),
    ("健身教练", False, (2024, 2026), "friend"),
]

# 按年份分阶段的语料池：这个人从「有劲」滑向「疲惫」，2022 是分水岭
POOLS = {
    "early": {  # 2019-2021
        "work": ["这个方案我想再改一版，我觉得还能更好", "我打算周末把原型做出来",
                 "我要试试那个新框架，感觉有意思", "这块我来吧，我想弄明白它到底怎么回事",
                 "好的收到", "我下午发你", "我觉得可以试试看", "我这边没问题",
                 "我准备把架构重构一下，现在这样太别扭了"],
        "family": ["妈我挺好的你别担心", "我下个月回去看你们", "我最近在学做饭哈哈",
                   "钱够花的你别老给我打", "我这周末有空，视频吧"],
        "friend": ["周末爬山去不去，我想出去走走", "我最近在读一本挺好的书",
                   "哈哈哈笑死我了", "约啊，我请客", "我最近状态还行，就是有点忙",
                   "我想明年换个城市试试"],
        "partner": ["今天想你了", "晚上一起吃饭吧我做", "我们下个月去趟海边好不好",
                    "刚才那事我不该那么说，对不起", "我喜欢和你聊这些"],
    },
    "late": {  # 2023-2026
        "work": ["好", "收到", "我改", "行", "我尽量", "这个我必须今天弄完",
                 "没办法只能先这样", "我知道了", "应该来得及吧", "我加个班弄完",
                 "抱歉我这边耽误了", "不好意思刚看到"],
        "family": ["嗯", "我挺好的", "最近有点忙", "过年再说吧", "妈我先忙",
                   "知道了", "下次吧，最近实在抽不开身"],
        "friend": ["改天吧", "最近太累了", "有点忙，等我忙完这阵",
                   "算了", "无所谓", "都行你定", "我也不知道我在干嘛",
                   "从下个月开始我一定要好好锻炼", "我怎么感觉这几年一点长进都没有",
                   "大家都这样吧，正常人到这个年纪不都这样"],
        "partner": [],
    },
}

NIGHT_LATE = ["睡不着", "我最近总觉得很累但又说不上来哪累",
              "有时候觉得这样过下去也挺没意思的",
              "我是不是浪费了太多时间", "算了不说了，晚安",
              "我不知道我到底想要什么，可能我根本就没想过"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="./work-demo/raw.jsonl")
    ap.add_argument("--n", type=int, default=9000)
    args = ap.parse_args()

    start = datetime(2019, 3, 1)
    end = datetime(2026, 6, 30)
    span = (end - start).days

    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    n = 0
    with open(args.out, "w", encoding="utf-8") as f:
        for _ in range(args.n):
            d = start + timedelta(days=R.randint(0, span))
            yr = d.year
            era = "early" if yr <= 2021 else "late"

            avail = [c for c in CONTACTS if c[2][0] <= yr <= c[2][1]]
            name, grp, _, kind = R.choice(avail)
            pool = POOLS[era][kind] or POOLS["early"][kind]

            # 2022 之后深夜比例明显上升
            if era == "late" and R.random() < 0.22:
                hour = R.choice([0, 1, 1, 2, 2, 3])
                text = R.choice(NIGHT_LATE) if R.random() < 0.35 else R.choice(pool)
            else:
                hour = R.choice([9, 10, 11, 12, 14, 15, 16, 17, 18, 19, 20, 21, 21, 22, 22, 23])
                text = R.choice(pool)

            ts = d.replace(hour=hour, minute=R.randint(0, 59), second=R.randint(0, 59))

            # 别人说的话也写进去，正好检验「只留自己的」这一步真的在过滤
            is_me = 1 if R.random() < 0.5 else 0
            if not is_me:
                text = R.choice(["嗯嗯", "好的", "行", "在吗", "你怎么想",
                                 "最近怎么样", "这个我看下", "OK"])

            f.write(json.dumps({
                "CreateTime": int(ts.timestamp()),
                "IsSender": is_me,
                "StrContent": text,
                "talker": name + ("@chatroom" if grp else ""),
                "Type": 1,
            }, ensure_ascii=False) + "\n")
            n += 1

        # 掺一些噪声，检验清洗规则
        for junk in ['<?xml version="1.0"?><msg><appmsg></appmsg></msg>', "[图片]",
                     "[动画表情]", "你已添加了对方，现在可以开始聊天了",
                     "https://example.com/a/b/c", "[语音]", "wxid_abc123"]:
            f.write(json.dumps({
                "CreateTime": int(datetime(2023, 5, 1, 12).timestamp()),
                "IsSender": 1, "StrContent": junk, "talker": "同事小李", "Type": 1,
            }, ensure_ascii=False) + "\n")
            n += 1

    print(f"[✓] {args.out}（{n:,} 条合成数据，含别人说的与噪声）")
    print("    这是虚构角色，不含任何真人信息")


if __name__ == "__main__":
    main()
