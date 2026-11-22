---
title: LitPilot
emoji: 📚
colorFrom: indigo
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
short_description: 文献综述智能体：每条结论都能回原文核对
---

# LitPilot

面向本科生的文献综述智能体：给它一个题目，它检索近五年论文、逐篇抽取 method / dataset / metric、
生成对比表，并**把每条结论对回原文**，标出证据等级（A 逐字命中 / B 近似命中 / C 不可核对 / D 无出处）。
全过程写入 JSONL trace，可在页面上一格格回放。

第六届厦门大学人工智能挑战赛参赛作品（2026-12-05）。

## 30 秒跑起来

```powershell
cd D:\lkj15\Documents\LitPilot
python scripts\run_dev.py          # 打开 http://127.0.0.1:8000
```

不需要联网、不需要 API key：默认 **离线语料模式**（5 篇合成论文，含一次注入的下载超时）。
想让模型真的跑，复制 `.env.example` 为 `.env` 填 `DEEPSEEK_API_KEY`，然后取消页面上「离线语料」开关。

## 它到底做了什么

| 步骤 | 工具 | 产物 |
|---|---|---|
| 1 规划 | Planner | 5 个子任务 + 2–3 条检索式 |
| 2 检索 | `search_papers` | ≤5 篇候选（近 5 年，arXiv） |
| 3 取全文 | `fetch_pdf` | PDF 落盘；失败→降级为仅摘要 |
| 4 切章节 | `parse_sections` | 带页码的章节文本 |
| 5 抽取 | `extract_claims` | method/dataset/metric + 结论 + **逐字引用句** |
| 6 成表 | `build_table` | 字段对齐的对比表，每行标最弱证据等级 |
| 7 校验 | `verify_citation` | A/B/C/D 等级、页码、覆盖度 |
| 8 复核 | Critic | C 级 → 重拉全文 → 重抽取 → 重校验（≤2 次），仍失败则排除但保留可见 |

## 关键设计（答辩会问的三件事）

**为什么不做向量库 RAG？** 综述要的是跨篇**字段级对齐**（谁的 dataset 和 metric 可比），
不是"找相似的 chunk"。相似度检索回答不了"这两篇的方法差在哪"。

**证据等级怎么定？** 归一化（空白、连字符、弯引号）后做子串命中 → A；找不到再做有序字符覆盖度
≥0.95 → B；只有摘要或定位不到 → C；没有引用句 → D。只有 A/B 进结论。
代码见 `tools/verify_citation.py`，规则是确定性的，同样的输入永远同样的等级。

**失败了怎么办？** 每个工具失败都抛 `ToolError`，executor 把它变成一条 trace 事件并降级，
不吞异常。演示里第三篇论文会超时一次，你能看到"超时 → 仅摘要 → C 级 → 重拉 → A 级"整条链路。

## 指标

| 指标 | 定义 | 离线语料 | 真实 arXiv + DeepSeek（5 篇，70.7s） |
|---|---|---|---|
| CCR 引用可核对率 | A/B 级结论数 ÷ 结论总数 | 93.8%（15/16） | 100%（25/25，A23/B2） |
| 字段完整率 | method+dataset+metric 齐全的篇数 ÷ 参与抽取篇数 | 100% | 60%（3/5） |
| 证据等级分布 | A/B/C/D 条数 | A14 / B1 / C1 / D0 | A23 / B2 / C0 / D0 |
| 失败可见率 | 有 trace 记录的失败数 ÷ 失败总数 | 100% | 100%（1 次注入超时，Critic 修复 5 条） |

> **CCR 高 ≠ 结论可信。** CCR 只回答"这句话的引用句能不能在原文里找到"，
> 不回答"引用句是否真的支持这句话"。真实运行里 CCR 100% 意味着模型抄引句抄得很准，
> 不意味着它没有过度概括。这条局限必须写进报告，答辩时主动说，比被问出来强。


## 怎么分享给别人看

三档，按场景选。**比赛现场只用第 1、2 档**：公网隧道依赖别人的服务，不能押在答辩上。

### 1) 本机（自己演示）

```powershell
python scripts\run_dev.py            # http://127.0.0.1:8000
```

### 2) 同一 wifi（队友、现场评委的手机/笔记本）

```powershell
$env:LITPILOT_HOST="0.0.0.0"
python scripts\run_dev.py            # 启动时会打印局域网地址，如 http://10.125.48.210:8000
```

队友第一次访问可能被 Windows 防火墙挡住，管理员 PowerShell 放行一次即可：

```powershell
netsh advfirewall firewall add rule name="LitPilot 8000" dir=in action=allow protocol=TCP localport=8000
```

> 局域网里任何人拿到地址都能跑，会烧你的 API 额度。设个口令：
> `.env` 里写 `LITPILOT_SHARE_TOKEN=litpilot2026`，之后地址变成 `http://10.125.48.210:8000/?k=litpilot2026`，
> 首访写 cookie，之后刷新、SSE 都自动带凭证。

### 3) 公网临时链接（给不在同一网络的人看，仅演示用）

不需要装任何东西，用系统自带 ssh 把本机端口反代出去：

```powershell
ssh -T -R 80:localhost:8000 nokey@localhost.run
```

十几秒后它会打印一行 `https://xxxx.app.lhr.life tunneled with tls termination`，
把 `https://xxxx.app.lhr.life/?k=litpilot2026` 发给对方即可（记得带口令）。

注意事项（都踩过）：

- **地址每次重连都会变**，别把它写进 PPT；演示当天重开就拿当次的地址。
- 链接靠一个 ssh 进程活着，**关掉终端就断**；笔记本一睡也断。
- 本机网络下 GitHub 直连被断，所以 `cloudflared` 的 exe 下不下来；
  `serveo.net` 能连上但边缘返回 502。`localhost.run` 是实测可用的那条。
- 公网链接下 SSE 是通的（实测 38 条事件 5.1 秒流完），但会慢一点。

### 4) 打包成 zip 发人：一个网址就够

服务自己在 `/download/litpilot.zip` 现打包（源码 + 网页 + 文档，60 KB，**不含 `.env`**）：

```text
https://xxxx.app.lhr.life/download/litpilot.zip
```

顶栏那个「下载源码包」按钮走的就是这条路由；本机也可以直接点。
命令行版：`python scripts/build_zip.py` → `dist/litpilot-<时间>.zip`。

### 5) 要一个不会变的地址：部署到云上

隧道地址会轮换、关终端就断，只适合"队友现在想看"。比赛当天要一个固定链接，看
**[docs/部署.md](docs/部署.md)**：Hugging Face Spaces（免费、十分钟、无需信用卡）和
Fly.io（要卡、更可控、能保住 trace）两条路，配置都已写好（`Dockerfile`、`requirements.txt`、
`fly.toml`、`scripts/hf_space_export.py`），照着命令贴即可。

部署前记得设 `LITPILOT_SHARE_TOKEN`（否则公开链接 + 你的 key = 别人替你花钱）和
`LITPILOT_RUN_BUDGET`（按天限次，默认 40）。


## 文件都是干什么的

```
config.py        路径、模型、超时、数量上限（唯一可调参数入口）
schema.py        数据契约（Paper/Field/Evidence/Claim/TableRow/Metrics/TraceEvent）
planner.py       五步计划 + 检索式扩展（模型不可用时自动降级为规则）
executor.py      主循环 + Critic 复核
trace.py         JSONL 逐行写盘 + SSE 队列
llm.py           DeepSeek chat/completions 调用，JSON 模式 + 重试
mockdata.py      离线语料（5 篇，含一条 B 级、一条永远 C 级的引句）
tools/           六个工具，一个文件一个
app.py           FastAPI：/api/runs、/stream(SSE)、/result、/tools、/health
web/             原生 HTML/CSS/JS，无构建链
scripts/         bootstrap_deps.py（沙箱内装依赖）、run_dev.py、smoke_*.py
data/            PDF / 检索 / 正文缓存 + runs/*.jsonl（trace）与 *.json（结果）
```

## 接口

```
POST /api/runs                    {topic, mock?, inject_fault?} -> {run_id}
GET  /api/runs/{id}/stream        SSE：先回放 JSONL，再接实时队列
GET  /api/runs/{id}/result        {status:"done", metrics, table, claims, ...}
GET  /api/runs                    历史运行
GET  /api/tools                   六个工具的名字与说明
GET  /api/health                  llm_ready / model / 默认模式
```

页面支持 `http://127.0.0.1:8000/?replay=<run_id>` 直接回放某次运行——写进报告或答辩时当链接用。

## 自检

```powershell
python scripts\smoke_exec.py     # 纯后端跑一轮，断言 A/B/C 等级与重试
python scripts\smoke_web.py      # 起服务后跑 HTTP/SSE 全链路
```

## 环境

- Python 3.12（DSH 自带运行时；系统 3.13 也能跑）
- 依赖装在 `.packages/`，由 `scripts/bootstrap_deps.py` 用 urllib 下载 wheel 解压安装
  （本机 pip 的临时目录被沙箱拒绝写入，故不用 pip/venv）
- 模型：DeepSeek `deepseek-chat`，JSON 输出模式
