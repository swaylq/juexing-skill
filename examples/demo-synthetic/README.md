# 示例：合成语料的跑通结果

**这里没有任何真人数据。** 全部来自 `tools/make_demo.py` 造的虚构角色——
一个 2019 年入职、2022 年经历某个转折、之后说话变短变晚的编造人物。

存在这里的目的：让你不用交出自己的聊天记录，就能看到这个工具的输出长什么样。

## 复现

```bash
python3 tools/make_demo.py   --out ./work-demo/raw.jsonl
python3 tools/extract_me.py  --input ./work-demo/raw.jsonl --out ./work-demo
python3 tools/stats.py       --in ./work-demo/me.jsonl --out ./work-demo
python3 tools/sample.py      --in ./work-demo/me.jsonl --stats ./work-demo/stats.json --out ./work-demo
```

随机种子固定，结果每次一致。

## 文件

| 文件 | 是什么 |
|---|---|
| `stats.md` | 数字层全文。**这是报告的唯一事实底座** |
| `sampling.json` | 抽样规则与覆盖率——用来质疑抽样有没有骗你 |
| `corpus-excerpt.md` | 抽样原话的开头一段（完整版含 572 句） |

## 这个例子里工具抓到了什么

从 9,007 条原始记录（含别人说的 4,536 条 + 7 条噪声）里：

- 保留 4,201 条**自己说的话**，别人的一条都没进来
- 自动检测出 **2022 年的转折点**：均长 10.4→7.4 字、深夜占比 0%→21%、
  「大家都这样」从 0 涨到每千字 21.6
- 发现**「我想 / 我要 / 我打算」从 2023 年起一次都没再出现**（义务÷意愿 = ∞）
- 找出「唯一会说好话的那个人 2022 年就淡出了」

注意这些全部是**计数**，不是解释。解释是后面模型的活，而且要过八道闸。
