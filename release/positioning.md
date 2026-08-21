# 蜂鸟 / Hummingbird — 定位与推广角度

> v1.0.0 · 2026-08-21 · 供各平台发布稿统一定调使用

## 一句话定位

**一个跑在普通笔记本上的本地 AI agent——不需要云 API,不需要 4090。**

> EN: *An AI agent that runs on the laptop you already own. No cloud, no datacenter, no 4090.*

## 为什么是"普通笔记本"这个角度

主流 agent 框架(Claude Code、OpenAI 生态、各种 MCP 编排器)几乎都以"你有云模型 / 有大显存"为前提。
蜂鸟是反过来的:**它是为小模型(0.5–9B MoE)和核显机器优化设计的**,目标是 95% 没有独显的人。

这不是降级,而是一个诚实的技术命题:

> 小模型不能自己 debug——所以 harness 替它补上;
> 小模型上下文贵——所以按类别只加载用得到的工具(扁平 prefill);
> 小模型会对着"你好"表演工具调用——所以问答/任务分层,闲聊就闲聊,任务才上全套工具。

## 产品支柱(按说服力排序)

| # | 支柱 | 一句话卖点 | 证据 |
|---|------|-----------|------|
| 1 | **硬件宽容** | 实测 核显笔记本跑 agent,共享内存有限的核显 也能稳定长任务 | 39 轮 V1–V39 基准、三模型横评 |
| 2 | **全离线·隐私** | 数据从不离开本机;断网照常干活 | 架构设计 |
| 3 | **扁平 prefill** | 工具按类别按需加载,上下文开销 -50%+,每次请求更快 | 设计文档 |
| 4 | **问答/任务分层** | 寒暄不会变成 20 步工具演示;真任务才解锁全套工具 | 实测修复"你好"循环 |
| 5 | **韧性 harness** | `.bak` 自动回滚、精确 pytest 失败注入、重复调用拦截、安全门(拦 rm -rf/系统路径) | V38b 实验、安全门测试 |
| 6 | **开箱即用的语音** | 本地 STT 模型随安装包自带,约 20× 实时,纯 CPU | 实测 |
| 7 | **可扩展** | skills + MCP 双扩展机制,`AGENTS.md` 写给 AI 看的接入文档 | 文档 |
| 8 | **双语言分发** | 蜂鸟(中文)/ Hummingbird(英文)两个安装包,命名清晰 | 安装包 |

## 目标人群(ICP)

1. **Ollama 玩家/本地模型爱好者**——已经在小模型上折腾,缺一个真正能干活的前端 agent(HN/Reddit 主战场)。
2. **隐私敏感用户 / 企业内网**——数据不能出本机,想要离线 agent(隐私叙事)。
3. **低配硬件用户**——笔记本没有独显,又想要"AI 打工"体验(中文 B站/知乎叙事)。
4. **小模型 agent 开发者**——关注 harness 设计(扁平 prefill、问答分层、韧性),会来读代码。

## 语气(voice)

- 诚实、工程师口吻、不吹"AGI"。
- 承认小模型的局限,把"harness 补位"讲成亮点而不是遮羞布。
- 有观点:"大模型 agent 很棒,但那不是全部人的机器。"
- 中文发布稿用大白话,不堆术语。

## 三组可复用文案(直接搬运)

### 中文
- 标题:蜂鸟——不挑显卡的本地 AI agent,普通笔记本也能干活的 agent
- 副标题:全离线 · 核显实测 · 小模型专用 harness · 自带本地语音
- 结尾钩子:别再用"我电脑跑不动"当不用的理由了——蜂鸟就是给 95% 的人做的。

### English
- Title: **Hummingbird — an AI agent that runs on the laptop you already own**
- Subtitle: Fully offline · tested on AMD iGPU · a harness built for small models (0.5–9B) · local STT bundled
- Closing hook: *The best model in the world is useless if your machine can't run it. We built the agent for the machine you have.*

### 一句话给 Product Hunt tagline
- EN: *A capable, fully-offline AI agent for laptops without a GPU — small models, smart harness.*
- ZH: *不挑显卡的全离线 AI agent:小模型 + 聪明 harness,普通笔记本也能跑。*

## 谁不该用(也是卖点的一部分)

- 有 4090 / 云端预算的人,可以直接用大模型 agent——蜂鸟不是替代品,是"人人可用"的补位。
- 诚实说明:复杂多文件重构、超长自主任务,小模型上限在;但 80% 的日常 agent 活儿(文件管理、查资料、写脚本、跑测试、整理)完全能打。

## 发布资产清单

| 资产 | 文件 | 状态 |
|------|------|------|
| 定位文档 | `release/positioning.md` | ✅ |
| GitHub README(EN) | `release/github/README.md` | 待写 |
| GitHub README(中文) | `release/github/README_zh.md` | 待写 |
| HN 帖子 | `release/launch/hn-post.md` | 待写 |
| Reddit(r/LocalLLaMA + r/selfhosted) | `release/launch/reddit-post.md` | 待写 |
| Product Hunt 列表 | `release/launch/producthunt-listing.md` | 待写 |
| B站脚本 | `release/launch/bilibili-script.md` | 待写 |
| 发布检查清单 | `release/launch/checklist.md` | 待写 |
| 截图 | `release/screenshot-*.png` | ✅ |
| 社交预览 | `release/preview-*.png`(1280×640) | ✅ |
