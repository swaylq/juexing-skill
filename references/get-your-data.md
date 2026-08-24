# 怎么拿到你自己的聊天记录（2026 年 8 月实况）

**先说最重要的一句：2026 年，微信导出工具的大半个生态已经被封死了，
但还剩一条稳路——iPhone 未加密备份（路线 B）。微信是本 skill 的主场景，从那条走。**
其余来源（iMessage、Telegram、日记）用来补充语料或做后备，可以混用。

---

## 一、微信这条路发生了什么

2026 年 1 月 8 日起，腾讯向 GitHub 提交了一系列 DMCA 通知，
针对的是所有微信聊天记录导出与解密工具。规模：

| 时间 | 覆盖范围 |
|---|---|
| 2026-01-08 | 一次点名 **4,195 个仓库**，含 PyWxDump、WeChatMsg、chatlog、wechat-dump-rs 等 |
| 2026-07-13 | 又一批，其中一个网络覆盖 1,464 个仓库 |
| 2026-07-27 | 七份通知，其中一个网络覆盖 643 个仓库 |
| 2026-08-04 | macOS 4.x 的 MCP 工具 wechat-cli |

腾讯的法律主张是：加密的数据库本身是**受版权保护的数据库汇编**
（通知里的原话是「包含 456 个字段、34 个分类的受保护数据库设计」），
因此即使你导出的是**你自己发的消息**，也构成规避技术保护措施。
用一句话概括他们的立场：**数据是你的，但你不许自己去拿。**

结果是几个最有名的项目**作者自己删了库**（不是被封，是主动清空以合规）：

| 项目 | 星数 | 现状 |
|---|---|---|
| LC044/WeChatMsg（留痕） | 41,996 | 代码已删空 |
| xaoyaoo/PyWxDump | 9,676 | 代码已删空，最后一次提交叫「删库跑路~」 |
| sjzar/chatlog | 9,184 | 代码已删空 |
| hicccc77/WeFlow | 13,917 | 代码已删空 |
| git-jiadong/wechatDataBackup | 6,400 | 代码已删空 |

**对你的实际影响**：这些工具就算你手上有旧版本，也已经无人维护，
会随着微信版本更新一点点失效。**不要把这个 skill 建在它们上面。**

---

## 二、按可靠程度排序的几条路

### 路线 A · Mac 自带的「信息」——最省事，也最合法（补充语料）

如果你用 iPhone + Mac，短信和 iMessage 全都在本地一个 SQLite 文件里，
**没有加密，没人对它发过 DMCA，苹果自己就允许你读**。

```bash
# 终端需要「完全磁盘访问权限」：
# 系统设置 → 隐私与安全性 → 完全磁盘访问权限 → 把「终端」勾上
python3 tools/adapters.py --source imessage --out ./work/raw.jsonl
```

字段 `is_from_me` 直接告诉你哪条是自己发的，不需要任何猜测。
缺点：中国大陆用户的主力不是 iMessage，语料量可能不够。

### 路线 B · iPhone 未加密备份 + WechatExporter ⭐ 微信主路线，从这条开始

[BlueMatthew/WechatExporter](https://github.com/BlueMatthew/WechatExporter)（8,398 星，GPL-2）
到今天**仍然存活**，因为它走的是完全不同的技术路径：
它不去内存里抠密钥，只是解析一份**你自己做的 iPhone 备份**。法律位置安全得多。

步骤：

1. iPhone 用数据线连 Mac；
2. 访达 → 选中你的 iPhone → 「将 iPhone 上的所有数据备份到这台 Mac」；
3. **「给本地备份加密」必须不勾**（勾了就读不出来）；
4. 备份完成后运行 WechatExporter，指向备份目录；
5. 导出成 HTML 或 TXT。

它的自己发的消息标记是 `Des` 字段，**`Des == 0` 表示是你发的**。

```bash
python3 tools/adapters.py --source wechatexporter \
    --input ~/Downloads/微信导出 --me-handle "你的微信昵称" --out ./work/raw.jsonl
```

**已知风险**：这个项目最后一个发布的可执行文件停在 2022 年，源码最后改动在 2025 年 2 月。
它能不能解析 2026 年当前版本的 iOS 微信数据库结构，**没有验证过**。
先拿一份最近的备份试一次，跑不通就换路线 A 或 D，别在这里耗。

### 路线 C · chatlog 本地接口——只在你已经装好、且微信版本够老时可用

chatlog 提供本地 HTTP 接口，默认 `http://127.0.0.1:5030`。两个必须知道的坑：

**坑一：CSV 导出没有「谁说的」字段。**
chatlog 的 CSV 列是 `Time,SenderName,Sender,TalkerName,Talker,Content` —— 没有 `isSelf`。
**必须用 `format=json`**，否则你根本分不出哪条是自己的。

**坑二：微信 4.x 上这个字段是猜的。**
Windows/Mac 微信 4.x 没有干净的布尔字段，chatlog 用 `status == 2` 加一堆条件推断，
**它的源码里自己标了 `// FIXME 不准`**。macOS 微信 3.x 的 `mesDes` 更坑——
**它的极性和 Windows 是反的**（0 = 自己发的）。

所以本 skill 的适配器默认拿 `sender` 是否等于你的 wxid 做交叉校验：

```bash
python3 tools/adapters.py --source chatlog \
    --me-handle "你的wxid" --trust sender --since 2018-01-01 --out ./work/raw.jsonl
```

**门槛（在 Mac 上很高）**：
- 提取密钥需要**关掉系统完整性保护（SIP）**——要进恢复模式跑 `csrutil disable`，
  这是实实在在地降低你机器的安全等级；
- 只支持 **macOS 微信低于 4.0.3.80** 的版本。当前微信 Mac 版是 4.1.x，**已经越过这个上限**；
- 重签名微信的做法会**弄坏微信的录屏权限和登录状态**；
- 而且代码已经从仓库删掉了，`go install` 装到的是墓碑。

一句话：**除非你已经有一套跑得通的旧环境，否则不要走这条路。**

### 路线 D · 别的平台——干净、合法、一键

分析引擎不在乎字是从哪来的。这些平台的官方导出功能完全正当，没有任何灰色地带：

| 平台 | 怎么导 | 自己发的标记 |
|---|---|---|
| Telegram | 桌面版 → 设置 → 高级 → 导出聊天记录 → JSON | `from_id` |
| WhatsApp | 单个聊天 → 更多 → 导出聊天 | 显示名 |
| Discord | 设置 → 隐私 → 请求我的数据 | 官方包 |
| QQ | 聊天记录 → 导出为文本 | 显示名 |

```bash
python3 tools/adapters.py --source telegram --input result.json --out ./work/raw.jsonl
python3 tools/adapters.py --source whatsapp --input ./聊天 --me-handle "你的名字" --out ./work/raw.jsonl
```

### 路线 E · 什么导出都没有也能跑

这个 skill 真正需要的只是**足够多的、你自己写下的、带时间戳的字**。
聊天记录只是最容易凑够量的一种。这些同样算数：

- 日记、笔记（Obsidian / Notion / 备忘录导出）
- 公众号草稿、博客、豆瓣广播、微博存档
- 发件箱里你写的邮件
- 朋友圈存档
- 甚至是你的 git commit message（如果你写得像人话）

```bash
python3 tools/adapters.py --source plain --input ~/我的日记 --out ./work/raw.jsonl
```

样本量低于 1,000 条时统计层不可信，报告会自动降级——但**编年那一章照样成立**，
因为纵向自比不需要大样本，只需要跨度。

---

## 三、微信自己的导出功能

微信客户端的「聊天记录迁移与备份」备份出来的是加密文件，**只有微信自己能读回去**，
无法用于分析。个别版本的「导出聊天记录」只能按单个会话导出成图片或文件，
量大时不现实。截至 2026 年 8 月，微信没有提供可用的个人数据导出接口。

---

## 四、下一步

不管走哪条路，拿到 `raw.jsonl` 之后都是同一条流水线：

```bash
# 1. 只留自己的话 + 脱敏
python3 tools/extract_me.py --input ./work/raw.jsonl --out ./work

# 2. 算数字
python3 tools/stats.py --in ./work/me.jsonl --out ./work

# 3. 抽样
python3 tools/sample.py --in ./work/me.jsonl --stats ./work/stats.json --out ./work
```

`work/` 目录里会自动生成 `.gitignore`，把整个目录挡在版本控制之外。
`NAMEMAP.local.json`（代号与真名的对照表）权限被设成 `600`，
**不要外传、不要进 git、不要贴给任何模型。**

---

## 五、一句法律提醒

分析**自己**的聊天记录，和分析**别人**的聊天记录，是两件完全不同的事。
前者主体即用户，同意问题天然成立；后者在中国法下涉及个人信息与人格权，
2026 年那一波「蒸馏别人」的开源项目已经引来过公开质疑。

**这个 skill 从第一步就把别人说的话全部丢弃，一个字都不进入后续流程。**
这既是分析方法——只有你自己说的话才反映你——也是一条不打算越过的线。
