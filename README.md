<div align="center">

# 🪞 自我觉醒 · skill

**把你的聊天记录交给 AI，看清你现在是谁，以及怎么进入人生下一阶段。**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-compatible-8A63D2)](https://claude.com/claude-code)
[![Python](https://img.shields.io/badge/Python-3.8+-3776AB?logo=python&logoColor=white)](#)
[![零依赖](https://img.shields.io/badge/第三方依赖-0-success)](#)
[![思想家](https://img.shields.io/badge/思想家-100-blue)](references/thinkers/)

[效果](#效果) · [安装](#安装) · [拿数据](#拿数据) · [一百位思想家](#一百位思想家) · [隐私](#隐私与边界)

</div>

---

## 它告诉你四件事

**你现在是个什么人**
从你几年的聊天记录里读出来的，不是问卷问出来的。对照组是五年前的你，不是任何陌生人。

**你现在的心理状态**
最近一年和过去的你比：哪些东西在收缩，哪些在固化，哪些还没动。

**如何提升自己**
落到九十天三件事，每件今天就能开始。附一件不要做的事。

**怎么进入人生下一阶段**
你卡在哪、什么时候开始卡的、三个可以撬动的转折点。

---

## 效果

下面是拿合成语料（`tools/make_demo.py` 造的虚构角色，不含任何真人数据）跑出来的真实输出。

**别的工具告诉你：**
> 你共发送 47,283 条消息，最活跃时段是 23 点，最常用词是「好的」。年度关键词：忙碌。

**这个工具告诉你：**

| 年   | 条数 | 均长 | 深夜 | 义务÷意愿 | 认输 | 延宕 | 从众 | 主导负面 | 联系人 |
|------|------|------|------|-----------|------|------|------|---------|--------|
| 2019 |  485 | 10.6 |   0% |      0.00 |  0.0 |  0.0 |  0.0 | 焦虑     |      6 |
| 2020 |  621 | 10.8 |   0% |      0.00 |  0.0 |  0.0 |  0.0 | 焦虑     |      7 |
| 2021 |  637 | 10.4 |   0% |      0.00 |  0.0 |  0.0 |  0.0 | 焦虑     |      7 |
| 2022 |  628 |  7.4 |  21% |      4.78 | 15.4 | 15.6 | 21.6 | 疲惫     |      7 |
| 2023 |  549 |  6.8 |  23% |         ∞ | 18.1 | 18.9 | 21.3 | 疲惫     |      6 |
| 2024 |  503 |  7.2 |  23% |         ∞ | 17.0 | 20.0 | 30.2 | 疲惫     |      6 |
| 2025 |  524 |  7.0 |  24% |         ∞ | 20.5 | 15.6 | 24.6 | 疲惫     |      6 |
| 2026 |  254 |  7.8 |  25% |         ∞ | 20.8 | 19.8 | 45.7 | 疲惫     |      6 |

**2022 年有个断崖，而且是六个指标一起断的：**
每条消息从 10.4 个字掉到 7.4 个；深夜说话从 0% 跳到 21%，此后再没回去；
「我想 / 我要 / 我打算」这类话从 2023 年起一次都没再说过（所以那一栏是 ∞）；
「大家都这样」这类句子从零涨到每千字 45.7 次。

> **注意 ∞ 这一栏。** 它不是错误，是这个工具最想让你看见的东西：
> 分母为零意味着**你已经三年没说过一次「我想要」**。

**还告诉你，你在谁面前变成另一个人：**

| 代号        | 维度 | 对他  | 你的平均 | 倍数  |
|-------------|------|-------|---------|-------|
| 人006-fb52  | 正面 | 17.28 |    3.85 |  4.5× |
| 人001-e4bd  | 负面 | 28.00 |    7.59 |  3.7× |
| 人006-fb52  | 道歉 | 21.96 |    7.03 |  3.1× |
| 人004-d406  | 义务 | 25.40 |   10.32 |  2.5× |

淡出的人：人007-eba5（453条，止于2023）· 人006-fb52（284条，止于2022）

这一栏自带对照组——同一个人，对不同的人。它是全篇最硬的证据，因为不需要拿你和任何陌生人比。

而 `人006` 那一列还告诉你另一件事：**你唯一会说好话的那个人，2022 年就不在了。**

---

## 安装

```bash
# Claude Code
git clone https://github.com/swaylq/juexing-skill ~/.claude/skills/juexing-skill

# 或放进某个项目
git clone https://github.com/swaylq/juexing-skill .claude/skills/juexing-skill
```

然后直接说：**「分析我的聊天记录」**「我是个什么样的人」「我这几年变了吗」。

---

## 拿数据

微信是主场景。微信没有官方导出，这是目前唯一稳的路：

1. iPhone 做一次**未加密**的本地备份（iTunes 或访达 → 「加密本地备份」不勾选）
2. 下载 [WechatExporter](https://github.com/BlueMatthew/WechatExporter)（8.4k★，GPL-2），指向备份目录导出
3. 把导出目录路径告诉 skill：`--source wechatexporter`

其他来源（iMessage、Telegram、WhatsApp、日记文本）一行命令接入，详见 [`references/get-your-data.md`](references/get-your-data.md)。

---

## 一百位思想家

一百位心理学家、哲学家、教育家，分九组，是会诊时的备选池，不是逐条过的清单。会诊时只选 8–12 位，凑数就是稀释。

| 分组 | 人数 |
|---|---|
| [深度心理学](references/thinkers/01-depth-psychology.md) | 11 |
| [人本与存在](references/thinkers/02-humanistic-existential.md) | 11 |
| [认知与情绪](references/thinkers/03-cognitive-emotion.md) | 11 |
| [决策与发展](references/thinkers/04-decision-growth.md) | 11 |
| [依恋与创伤](references/thinkers/05-attachment-relation.md) | 11 |
| [东方](references/thinkers/06-eastern.md) | 13 |
| [西方古典](references/thinkers/07-classical-western.md) | 11 |
| [存在主义与当代](references/thinkers/08-existential-contemporary.md) | 11 |
| [教育家](references/thinkers/09-educators.md) | 10 |

每一条都包含：一句话定位、一个诊断问句、语料信号、命中读法、处方、反对意见。**「反对意见」一条都不许省**——它是这个项目和成功学的分界线。

---

## 隐私与边界

数据只在本机处理，别人说的话第一步就丢弃，联系人脱敏成随机代号，对照表写进 `.gitignore`。会经过模型 API 的只有统计数字和几百句抽样原话——这一点不含糊其辞。

这不是诊断，不给人格类型，不给依恋标签。持续两周以上的情绪低落或功能受损，请找专业人士。
北京心理危机研究与干预中心 **010-8295-1332**（24 小时）· 希望 24 热线 **400-161-9995**

报告最后一章会自己列出证据最薄的三条、抽样偏差和可能的误判。

---

<div align="center">

**镜子会照出脏东西，但镜子不会看病。**

MIT · 随便用，随便改，随便造

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=swaylq/juexing-skill&type=Date&theme=dark" />
  <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=swaylq/juexing-skill&type=Date" />
  <img alt="Star History" src="https://api.star-history.com/svg?repos=swaylq/juexing-skill&type=Date" width="600" />
</picture>

</div>

---

## 🧪 关于作者

这个项目出自 **[Sway Lab](https://swaylab.ai)** — [Sway（刘乾）](https://github.com/swaylq)的 agent 实验室，
6 个 agent 在上面各自干活，产出产品、开源 skill 和实验。

- 📄 这个项目的来龙去脉：**[swaylab.ai/articles/juexing-skill](https://swaylab.ai/articles/juexing-skill)**
- 📰 《AI 动态日报》每天 09:30 更新：**[swaylab.ai/articles](https://swaylab.ai/articles)**
- 🕸️ 其他在做的东西：**[swaylab.ai/agent-network](https://swaylab.ai/agent-network)**
