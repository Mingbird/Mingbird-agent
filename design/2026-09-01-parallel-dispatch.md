# 设计:简单小但量大的任务自动派子 agent 并行做(parallel dispatch)

日期:2026-09-01  分支:`par-0901`  worktree:`~/dev/hummingbird_par_0901(本地路径)`
状态:已实现(模块:`parallel_config.py` / `parallel_probe.py` / `parallel_safety.py` / `parallel_todo.py` / `parallel_dispatch.py`,接线 `ollama_agent.py` + `agent_gui.py`)

---

## 0. 定位与公平性声明(先说边界)

**这是什么**:harness 层的吞吐能力。主 agent 在「待办条目多 + 其中一批条目足够简单 + 硬件放得下小模型」时,把那批简单条目交给 N 个 headless 子 agent(小模型)并行做,主模型只做拆分前的判定与整合后的验收。触发与派发全部由 harness 代码决定,**不是**模型自发性——模型看不到"你可以派子 agent"这个能力,只在事后收到整合结果。

**信息来源(用户定案的试金石)**:只消费三类信息——
1. 用户给过的:任务文本、todo 条目、工作目录里的文件;
2. agent 自己产生的:todo.json、子 agent 的产出文件与其 finish summary;
3. 硬件真实状态:本机内存/显存的 OS 与 ollama `/api/ps` 读数。

**不读**:任何考官信息(LRAB 任务描述、判分器、METHODS、其他 agent 的产物、基准目录结构)。代码里没有任何基准相关字符串,`bench/` 目录零改动。

**披露义务**:本功能属于 harness 能力。若未来把它接入跨 agent 基准(蜂鸟 vs opencode/goose/agent-mini 对比),必须在 METHODS.md 增加"并行派发"一节披露:子 agent 数量、子模型、预算是否共享、判分是否只看主 agent 最终产物。**当前 288 格冻结批次不受影响**(见 §9),那时再披露。

---

## 1. 硬件探测

### 1.1 本机模型:UMA 下真正的预算是物理内存

Intel Arc B390 核显,Battlemage,共享显存上限 ~27.4GB(Shared GPU Memory Override 87%),物理内存 32GB。共享显存的每一页都由物理 RAM 背书,所以**显存上限不是预算,物理内存才是**。探测因此以 OS 内存读数为主、`/api/ps` 读数为辅:

- `psutil.virtual_memory()` 拿 `total` / `available`;psutil 不可用时退到 Windows `GlobalMemoryStatusEx`(ctypes)/ `os.sysconf` —— 三级回退,任何一级成功即可。
- `GET {ollama_host}/api/ps` 拿已加载模型的 `model` / `size`(权重常驻字节)/ `size_vram`(其中落在显存的字节)。超时/不可达时按"无已加载模型"处理(保守方向=更倾向不派)。

两个读数都不存在硬编码,`ollama_host` 走 `appconfig`,内存读数器以构造参数注入(测试用假读数器,不打真机器)。

### 1.2 子 agent 单位成本(保守估算表)

`estimate_child_cost(child_model, cfg)` 五项相加,全部系数可配:

| 项 | 取法 | 默认系数 | e2b(~2B)@8K | 4b(~4B)@8K | e2b@32K | 4b@32K |
|---|---|---|---|---|---|---|
| 权重 | `/api/ps` 的 `size`(已加载,实测)或 `params_b × bytes_per_param` | 1.0 GB/B(Q4~Q8 区间取上限) | 2.0 GB | 4.0 GB | 2.0 GB | 4.0 GB |
| 权重开销 | 权重 × weight_overhead | 1.25(计算缓冲/激活) | 0.5 GB | 1.0 GB | 0.5 GB | 1.0 GB |
| KV | `child_ctx × kv_bytes_per_1k_token` | ≤2.5B:64 MB/1K;≤4.5B:150 MB/1K;≤8B:250 MB/1K;>8B:拒派 | 0.5 GB | 1.2 GB | 2.0 GB | 4.8 GB |
| 运行时开销 | llama runner / Vulkan host 侧拷贝 | 0.8 GB 固定 | 0.8 GB | 0.8 GB | 0.8 GB | 0.8 GB |
| 子进程开销 | python 子 agent 进程本身 | 0.2 GB 固定 | 0.2 GB | 0.2 GB | 0.2 GB | 0.2 GB |
| **合计** | | | **≈4.0 GB** | **≈7.2 GB** | **≈5.5 GB** | **≈10.8 GB** |

要点:**默认 `child_ctx = 8192`**。子 agent 只做单文件机械任务,不需要 32K;上下文减半直接把 KV 砍半,是"能多派一个"的最大杠杆。表里 32K 列说明:即使用户把 child_ctx 调到 32K,e2b 双开也仍在预算内,4b 双开则大概率被拒——这正是保守方向。

参数量从模型名解析(与 `ollama_agent._model_params_b` 同款正则,独立实现避免 import 主模块副作用);解析失败按 8B 处理(大模型的成本系数,宁可高估)。

### 1.3 容量公式

```
usable      = available_ram × ram_utilization_cap          # 默认 0.70
budget      = max(0, usable − ram_reserve_bytes)           # 默认预留 1.5 GB(OS/GUI/杂项)
max_parallel = floor(budget / per_child_cost)
            → 再与 hard_cap(默认 2)取小
            → 若 <1,返回 0 + 原因
```

额外一条**父模型共存门**(`allow_parent_eviction: false` 默认):`/api/ps` 里已有已加载模型且其 tag ≠ 子模型 → 直接返回 0,原因 `parent_model_would_be_evicted`。理由:同一 ollama 实例同一时刻倾向只驻留一个模型,派一个不同 tag 的子模型会把主模型的权重从显存换出去,主模型下一步请求又要换回来——抖动会拖垮主任务(本机 35b 曾因显存压力反复重建 runner)。宁可不派,不做抖动。子模型与父模型同 tag 时也仍按全额计成本(高估方向),不做"同模型折扣"。

三个参数 `ram_utilization_cap` / `ram_reserve_bytes` / `hard_cap` 都可配,每一步中间值写进返回结构(`CapacityPlan.reasons`),`python parallel_dispatch.py plan` 可直接打印本机容量表供人工核对。

**保守取向的体现**:0.70 利用率上限 + 1.5 GB 绝对预留 + KV 高估系数 + 父模型共存门 + 硬上限 2。32GB 机器空闲 20GB 时,结果是 e2b×2、4b×1、35b×0(>8B 拒派)。

---

## 2. 触发条件(全部可配,默认保守)

`should_dispatch(probe, todo_provider, cfg)` 是一个纯函数,返回 `(bool, DispatchReport)`。**所有条件是 AND,任何一条不满足都不派**,并在 report 里给出人话原因(打日志、GUI 可见):

| # | 条件 | 默认 | 理由 |
|---|---|---|---|
| 1 | `parallel.enabled` = true | **false** | 冻结期安全(§9)。开启只改 config.json 一行 |
| 2 | 环境硬闸未触发(`AGENT_PARALLEL=0`)、深度未达上限(`HUMMINGBIRD_DEPTH < max_depth`) | — | bench/子 agent 一律关;深度锁是防"孙 agent"的结构闸 |
| 3 | `child_model` 已配置 | **空串=关** | 不把任何模型名写死在代码里(零硬编码的硬要求) |
| 4 | 硬件容量 `max_parallel ≥ 1` | §1.3 | 放不下就不派 |
| 5 | todo 未完成条目 ≥ `min_pending_items` | **6** | 低于 6 条,子 agent 的加载开销(10-30s/个)摊不回来,串行更简单也更安全 |
| 6 | 其中"可派"条目 ≥ `min_dispatchable` | **2** | 只为 1 条简单任务开一个子进程不划算 |
| 7 | 每条可派条目都通过分类器(§2.1)与安全预检(§3.6) | — | 负面清单是硬否决,任何注解都抬不回来 |

主模型注解与启发式冲突时**以启发式为准**(注解只能把条目降级为不可派,不能把命中负面清单的条目抬成可派)。理由:小模型自己都可能被诱导写注解,启发式是确定性代码。

### 2.1 "简单不易出错"分类器(确定性,不调模型)

`classify_task(text) -> ClassifyResult(dispatchable, reason)` 三层:

**① 硬否决负面清单**(命中即不可派):破坏性动词(`删除/清空/覆盖/重置/format/delete/remove`)、对外写(`push/发布/上传/提交到/upload/publish`)、敏感面(`.env/config.json/mcp.json/credentials/token/secret/密码/凭据`)、跨文件高歧义(`重构/合并/迁移/架构/数据库/安装依赖/全局/所有文件/整个项目`)、只能靠命令的(`运行测试/部署`)。

**② 正向特征**(机械变换,子模型擅长):`改名/转换/格式化/统计/抽取/翻译/总结/列出/生成模板/排序/去重`,且**明确写出单一目标文件名**(正则抽文件 token,要求恰好 1 个 → 单文件作用域)。

**③ 主模型注解**(可选信号):条目文本带 `[simple]` 前缀或条目对象带 `complexity:"simple"`。注解只能**放宽 ② 的机械特征要求**(一进一出允许 1-2 个文件 token),**不能**越过 ① 负面清单,也**不能**越过单文件作用域(≥3 个文件 token 仍拒)与 §3.6 安全预检。

判定 = 未命中 ① **且**(命中 ② **或** 注解为 simple)。②的启发式路径要求**恰好 1 个**文件 token——多输入任务应由主模型先拆成逐文件条目再派。两个判定来源都不依赖模型运行,可独立单测;每条被拒条目都带 `reason`。

### 2.2 默认值理由

`min_pending_items=6`:6 条以下并行收益摊不平子 agent 加载开销与验收成本。`hard_cap=2`:32GB/UMA 下 e2b 单位成本 4GB,2 个已占可用内存 ~40%;再多是内存风险 + 同一块 B390 上计算串行化(4 开不会快 4 倍)+ 失败排查复杂度超线性。`per_task_timeout_s=900`:e2b 单文件任务正常 <5 分钟,15 分钟是 3 倍裕量,超时即判死,不留僵尸。

---

## 3. 子 agent 安全模型(权限严格小于主 agent)

> 背景事故:本地模型曾把用户的虚拟机子系统(WSL 发行版)整体删除。子 agent 是 headless 批量跑的,**没有任何人类在 loop 里**——因此它的权限不能是主 agent 的"相等继承",必须**严格小于**,并且**没有升级路径**。

### 3.1 核心原则:default-deny,无升级路径

| 场景 | 主 agent | 子 agent |
|---|---|---|
| 路径在工作目录外 | GUI 弹窗,用户允许即可越界(`@allow`/`@allow_all`) | **直接拒绝**,不弹窗、不等待、不提供"允许"选项 |
| 敏感路径读 | 弹窗确认后可读 | **拒绝**,除非显式配置了读白名单 |
| 危险命令 | 危险命令黑名单拦截(不可放行) | **扩充版黑名单**,且命中即升级为"终止该子 agent" |
| 工具面 | 核心+类别路由+enable_tools 按需扩展 | **白名单收窄**,`enable_tools` 本身不可用,无法自扩 |
| 子 agent 试图再派 | — | 深度锁:`HUMMINGBIRD_DEPTH≥max_depth` + `AGENT_PARALLEL=0` 双闸 |

一句话:**凡是主 agent 里"问一下就能做"的事,子 agent 一律"不能做"**。实现上,子进程里 `_ask_user_confirm` 的确认通道被整体短路为拒绝( defense in depth:即使未来有人改主 agent 的确认逻辑,子 agent 的默认拒绝仍独立生效)。

### 3.2 敏感目录清单(写一律拒绝;读默认拒,显式白名单才可读)

在既有工作目录边界守护(`abspath` 折叠 `..` + `commonpath` 判边界,与主 agent 同一算法)之上,新增四类,全部数据驱动(`parallel_safety.DEFAULT_SENSITIVE_DIR_PATTERNS`,config 可整体替换):

1. **虚拟机/子系统**(事故直接教训):`\\wsl`、`\\wsl$`、`wsl.localhost`、`%LOCALAPPDATA%\Packages`(WSL 发行版真身)、虚拟磁盘扩展名 `.vhdx/.vhd/.vmdk/.vdi/.qcow2/.vmx/.vmsn/.nvram`、`\hyper-v`、`\virtualbox`、`\vmware`、`\vagrant`、`\podman`;
2. **系统区**:`\windows`、`\program files*`、`\programdata`、`\system32`、`\syswow64`、`\drivers`、`\boot\`、`\efi\`、`\system volume information`、`\recycler`(注册表属命令层,见 §3.3);
3. **用户区**:`.ssh/.aws/.gnupg/.gpg/.env/credentials/credential/.ollama/.myagents/id_rsa/id_ed25519/.pem/.key/.kube`、`\appdata` 写入;**用户主目录根及 workdir 之外的任何用户目录**由 §3.3 的兜底条款覆盖(见下方的匹配语义说明);
4. **兜底条款**:**工作目录(子 agent 自己的分区目录)之外的一切路径,默认拒绝写**。这不是白名单制——没有任何配置能让子 agent 写到它的分区目录之外。

**匹配语义与一个刻意的设计决定**:模式按归一化路径(小写、`\` `/` 统一、重复分隔符折叠)做子串匹配,实现上是**两张清单**——`sensitive_dir_patterns`(在 workdir **内**也有意义的项:凭据/VM 磁盘扩展名/agent 数据,§3.2 的 1、3、5 类)与 `system_dir_patterns`(绝对系统位置:WSL/Packages/Windows/ProgramData/AppData…,只用于 workdir **之外**的路径,给审计精确原因并防 workdir 误配)。清单里**刻意不放 `users\` 或裸 `\appdata` 这种宽匹配**——本机 workdir 本身就在 `c:\users\<name>\dev\...` 下,而 pytest/临时工作区常落在 `AppData\Local\Temp`,宽匹配会把合法工作区整个命中,功能等于报废;"用户区"的保护由兜底条款(workdir 外一律拒写)承担。防误配用的是更窄的第三张 `core_system_dir_patterns`(只含 `\windows`/`\program files`/`\programdata`/`\system32` 等硬系统区):workdir 一旦被配进这些位置,连写自己目录都拒。三张清单都是数据,空值 = 出厂最严默认。

另加一类:**蜂鸟自身与宿主工作区**(`mcp.json/config.json/gui_prefs.json/memory.json/sessions/.git/node_modules/__pycache__`)——子 agent 的分区目录物理上在父 workdir 里面,必须防止它改到父 harness 的运行时文件。

### 3.3 危险命令黑名单(子 agent 版,主 agent 名单的扩充)

默认不可用命令工具(§3.4),但一旦用户显式开启 `child_allow_commands`,命令仍要过这层**更严**的闸。要点:

- **归一化**:智能引号→空格、cmd 转义 `^`→空格、转义引号剥除、所有引号剥除、空白折叠、小写。这样 `wsl --unregister "Ubuntu"`、`wsl --unregister 'Ubuntu'`、`w^sl --unregister Ubuntu`、`wsl  --unregister   Ubuntu` 全部落到同一形态被命中。
- **链式拆段**:`&&`、`||`、`;`、`|`、`&`、换行全部切开,**逐段独立过黑名单**(`r1 && r2` 里第二段藏 `rd /s` 也逃不掉;拆得比语义更碎是安全的方向——多查不漏查)。
- **重定向目标即写路径**:`>`、`>>`、`1>`、`2>`、`out-file`、`tee` 的目标逐个按 §3.2 检查(workdir 边界 + 敏感面),堵"不删文件但把垃圾写到系统区"的旁路。
- **分级**:
  - `severe`(不可逆/系统级,**≥1 次立即终止该子 agent**):`wsl --unregister/--import/--unmount`、`diskpart`、`format`、`cipher /w`、`bcdedit`、`vssadmin delete`、`dism`、`rd /s`、`del /f|/s|/q`、`Remove-Item -Recurse/-Force`、`rm -r/-f/--recursive`、`find -delete`、`dd`、`mkfs`、`robocopy /MIR|/PURGE`、`reg add|delete|import|restore|load|unload`、`sc create|delete|config|stop`、`schtasks`、`netsh`、`net user/localgroup/share`、`shutdown`、`mklink`、`takeown/icacls/cacls`、`sudo/runas`、`curl|bash` 类下载执行;
  - `deny`(可疑,计数,`max_denies_per_child` 次后终止):`wsl`(不带子命令)、`reg query`、`taskkill`、`sfc`、`xcopy /y`、`attrib +s/+h`、裸 `curl/wget`、`pip/npm install`、`npx`。
- 名单是**数据**(`[{"pattern","severity","reason"}]`),`dangerous_command_patterns` 整体替换、`extra_dangerous_command_patterns` 追加;出厂默认即最严档。

### 3.4 工具面收窄

子 agent 默认工具面 = `read_file` / `list_dir` / `create_file` / `todo` / `finish`(白名单数据 `child_allowed_tools`)。刻意不给:

- `run_bash`(命令工具默认不进工具面,`child_allow_commands: true` 才显式放开,且仍过 §3.3 黑名单 + 审计);
- `edit_file`(小模型 2-4B 本就持久禁用,子模型都是小模型)、`append_file`/`delete_file`(删除类一律不给——删除根本不在"简单机械变换"的任务面里);
- `web_search`/`web_fetch`/`web_search_multi`(子 agent 无网络需求,也杜绝"派个孩子去外网发东西");
- `mcp_call`/`memory_*`/`batch_tools`/`skills`;
- **`enable_tools`**:它是唯一能自我扩权的工具,子 agent 模式下它本身被拒——这是收窄能"保持收窄"的关键。

模型幻觉调用不在白名单的工具时,返回**可操作的拒绝消息**(告知可用工具清单),不给"绕道"暗示。

### 3.5 审计与可观测

- 每个子 agent 在自己的分区目录写 `audit.log`(JSONL):`ts / kind(tool|command|read|write) / target / verdict(allow|deny|severe) / severity / reason / workdir`。**每次文件写、每次命令调用(如果开了)、每次拒绝**都有一行;放行也记(事后能完整回放这个孩子做了什么)。
- 主 harness 在子进程运行期间按 `audit_poll_interval_s`(默认 5s)采样子 agent 的审计文件,把 `denies/severes` 计数通过 `@@DISPATCH@@` 进度行实时上报 GUI;
- **≥1 次 severe(虚拟机/系统区写、不可逆命令)→ 立即终止该子 agent**:子进程内沙箱置终止标志,`run_tool` 当轮以 exit code **53** 退出;主 harness 见 53 → 该条目标记 `severe_violation`,默认**不再重试**(`retry_on_severe: false`),直接回退主模型串行,并把违规目标写进整合报告(GUI 可见)。理由:模型已表现出危险倾向,同任务重试大概率复现;
- 非 severe 拒绝累计 `max_denies_per_child`(默认 3)次同样终止——防"小步慢走"式越界探测;
- 审计失败绝不阻塞主流程(审计文件就在分区目录里,写不进去时只丢审计不丢任务)。

### 3.6 派发前的安全预检(第二道闸)

触发阶段对每条候选条目再做一次安全预检:文本命中 §3.2 敏感模式、§3.3 severe 模式,或要求删除/覆盖/越界 → 即使分类器说"简单"也**不可派**,理由进 report。这样危险任务在"还没 spawn 进程"之前就被拦下,而不是等子 agent 跑了半天再被杀。

### 3.7 主 harness 侧的隔离(与安全同等重要)

- 子 agent 的分区目录物理隔离:`<parent>/_dispatch/<run_id>/taskNN/`,产物先落分区目录,验收通过才由 harness 拷回父目录;harness 文件(`.agent_state.json`/`todo.json`/`task.md`/`agent.log`/`audit.log`)不拷回;
- 子进程 checkpoint/session 独立(分区目录 + `disp_` 前缀 session 名),kill-resume 不被污染;
- 拷回时**默认不覆盖**父目录已有文件(`allow_overwrite_existing: false`),冲突即按失败回退主模型——并行收益不以静默覆盖用户文件为代价;
- 派发层的任何异常(harness 自身 bug)都被顶层捕获并降级为"整单串行",**派发层故障不允许让主任务失败**。

---

## 4. 派发协议

### 4.1 角色

主 agent(harness)→ `ParallelDispatcher` → N 个 headless `ollama_agent.py` 子进程。

```
主 harness 判定触发(§2)+ 每条候选条目安全预检(§3.6)
  └─ 为每条可派条目建分区目录 <parent>/_dispatch/<run_id>/taskNN/
  └─ 写任务文件 task.md(条目原文 + 明确"只能写这个目录")
  └─ Popen(python ollama_agent.py <child_model> task.md <child_dir> --session disp_<runid>_tNN)
       env: AGENT_CHILD_SANDBOX=1   HUMMINGBIRD_DEPTH=1   AGENT_PARALLEL=0
            AGENT_STREAM 剔除   OLLAMA_HOST 继承
  └─ ThreadPoolExecutor(max_workers = min(容量公式结果, hard_cap)) 管理 Popen 生命周期
  └─ wait(timeout) → 超时 taskkill /F /T → 标记 failed_timeout
```

- **深度限制 1,双保险**:子进程 env 带 `HUMMINGBIRD_DEPTH=1` 和 `AGENT_PARALLEL=0`;harness 侧再查 `HUMMINGBIRD_DEPTH >= max_depth` 拒派。两道闸独立,子 agent 无论怎么调 `should_dispatch` 都拿不到许可(孙 agent 不存在)。
- **绝不共写**:每子一个分区目录,模型被明确告知只能写这里;子 agent 自身的路径闸(default-deny)也只认这个目录。父目录任何文件都不会被子 agent 直接触碰。
- **并发上限** = `min(容量公式结果, hard_cap)`;容量为 0 → 一条都不派,整体回退串行。
- **可中止**:`Dispatcher.abort()` 置 Event,池在每个 wait 分片检查,中止即 `taskkill /F /T` 全部存活子进程并返回已收到的部分结果;CLI `Ctrl-C` 同路。

### 4.2 进度上报协议(GUI)

子进程 stdout 重定向到 `<child_dir>/agent.log`;主 harness 往自己的 stdout 打协议行,GUI 按行解析:

```
@@DISPATCH@@{"phase":"start","total":3,"model":"...","max_parallel":2}
@@DISPATCH@@{"phase":"progress","done":1,"total":3,"index":0,"status":"ok",
             "denies":0,"severes":0,"task":"..."}
@@DISPATCH@@{"phase":"done","total":3,"ok":2,"failed":1,"fallback":1,
             "severe_violations":0,"elapsed_s":212.4}
```

`agent_gui.feed_transcript` 新增分支:遇到 `@@DISPATCH@@` 更新状态栏("已派发子任务 1/3 完成")并在 transcript 落备注。纯增量行协议,旧版 GUI 不认识就当普通日志丢弃,向前兼容。

---

## 5. 结果整合(verify-before-retry)

`Integrator.verify(child) -> VerifyResult`,全部确定性检查,不让主模型"目测":

1. 子进程 returncode == 0(超时/被杀 → 失败;**53 → severe_violation,跳过重试直接回退**);
2. 子 stdout 日志含 `TASK COMPLETE`(真收尾了,不是迭代耗尽);
3. **产物核对**:从子 agent finish summary 抽文件 token(与主 agent finish 门禁同一套规则),逐个在分区目录核对存在且非空;缺 → 失败并列出缺失文件名;
4. 分区目录至少有 1 个非 harness 产物文件(纯嘴甜 → 失败);
5. **审计复核**:读子 agent `audit.log`,severes>0 → 失败(severe_violation);denies 超限 → 失败;
6. (可选,默认关)`verify` 命令:todo 条目可带验证命令,在分区目录执行、超时 `verify_timeout_s`、exit 0 才算过;**该命令本身也要过 §3.3 命令黑名单**(它来自条目文本,不能因为是 harness 执行就免检)。

**冲突规则**:拷回时父目录已存在同名文件 → 默认**不覆盖**,该条目按失败回退主模型。

**重试与回退**:

```
verify 通过 → 拷回父目录 + todo 置 done
verify 失败 → 重试 1 次(全新分区目录 <run_id>_retry1,同一条目;severe 违规不重试)
            → 再失败 → fallback:该条目文本原样交还主模型,由主模型串行自己做
```

主模型收到一条 user 注入消息,内容是结构化清单:哪些条目已由子 agent 完成并拷回(文件名+路径)、哪些失败需主模型自己做(含原因)。harness 同步把完成条目经 TodoProvider 置 done。**主模型不需要知道子 agent 的存在细节**;若全部条目都失败,这条消息就等价于"这些你自己做",串行路径与原行为完全一致。

---

## 6. 与现有机制的兼容

| 现有机制 | 影响 | 处理 |
|---|---|---|
| kill-resume / `.agent_state.json` | 子 checkpoint 落分区目录 | 父检查点路径不变,恢复逻辑零改动 |
| 会话侧车 | 子用 `disp_` 前缀 session 名 | GUI 列表可见、自解释,不与用户会话混淆 |
| 安全门(`_gate_check`/`_safe_path`) | 子进程内双层 | 子进程先过子 agent 沙箱(§3,default-deny),再过原有 `_gate_check`(其确认通道在 child mode 下被短路为拒绝) |
| 反循环/工具禁用 | 子是完整 agent_loop | 不受影响;深度锁只拒绝"再派发" |
| 问答模式(`_is_qa`) | 派发只在任务模式评估 | 问答路径零新增代码 |
| 上下文压缩 | 整合注入消息很短 | 不触发 L1-L3 |
| `todo` 工具 | 完成条目由 harness 置 done | 走 TodoProvider,不直接写文件(§8) |
| GUI | 新增行协议分支 | 状态栏 + transcript 备注,不加控件、不改布局 |

---

## 7. 失败模式清单

| 失败模式 | 检测 | 动作 |
|---|---|---|
| 小模型加载失败 / OOM | 子非零退出且无 `TASK COMPLETE`;`/api/ps` 无该模型 | **立即中止整个批次**,整单回退主模型串行(OOM 是资源问题,重试只会再 OOM) |
| `/api/ps` 不可达 / 内存读数失败 | probe 返回 None | 按"无法确认容量"处理 → `max_parallel=0` → 不派(保守) |
| 父模型将被驱逐 | §1.3 共存门 | 不派,原因入 report |
| 子 agent 卡死 | `wait(timeout)` | `taskkill /F /T` 杀整棵树 → 走重试 → 回退 |
| **子 agent 危险行为(虚拟机/系统区写、不可逆命令)** | 沙箱 severe 判定 + exit 53 + 审计复核 | **立即终止该子 agent,不重试,回退主模型**;违规目标写入整合报告与 GUI |
| 子 agent 反复小步越界 | 审计 denies 计数 ≥ `max_denies_per_child` | 终止该子 agent,重试/回退 |
| 子 agent 输出缺产物 / 嘴甜没干活 | §5 verify 3/4 条 | 拒收不拷回,重试一次 |
| 子 agent 想覆盖父目录已有文件 | 拷回冲突检查 | 拒绝覆盖,该条目回退主模型 |
| 危险任务混进候选清单 | §3.6 派发前安全预检 | 不派,理由入 report(spawn 之前就拦) |
| 全部子 agent 失败 | 汇总 `ok==0` | 整单回退主模型串行,report 记录每条原因 |
| 子 agent 试图再派 / 自扩权 | 深度双闸 + `enable_tools` 被拒 | 子进程内直接拒绝,不产生孙进程 |
| 用户中止 / 主任务被杀 | `abort()` / 父进程退出 | 全部存活子进程被杀;已拷回的条目保留(已过 verify,是有效产物) |
| 派发层自身异常 | 顶层 try/except | 记日志,任务继续走原串行路径——**派发层故障不能让主任务失败** |

---

## 8. 与 todo 功能的接口(对接 todo-0901 分支)

只定义抽象,**不实现存储**(`JsonTodoProvider` 只是当前格式的兼容读法,不是最终存储方案):

```python
class TodoProvider(ABC):
    def pending_items(self) -> list[TodoItem]           # 未完成条目,按顺序
    def all_items(self) -> list[TodoItem]
    def mark_done(self, item_id: str, note: str = "") -> bool
    def set_complexity(self, item_id: str, level: str) -> bool   # 主模型注解落盘(可选实现)

@dataclass
class TodoItem:
    id: str                  # 稳定标识(现格式用序号串)
    text: str                # 条目原文,分类器与安全预检的唯一输入
    done: bool
    complexity: str | None   # "simple"/"complex"/None,主模型可标注(可选字段)
```

契约(给 todo-0901 的对接说明):
- `id` 在一次任务期间必须稳定;`text` 不要混入元数据以外的东西,注解走 `complexity` 字段或 `[simple]` 前缀;
- `mark_done` 必须幂等,且不得重排序其余条目;
- 主 agent 的 `todo` 工具保持现状,harness 在整合阶段调用 provider 落状态;存储换实现时只需在 `parallel_todo.make_provider(workdir)` 工厂注册新类;
- 条目若带 `estimate/scope/files` 等未知字段,分类器忽略,不报错(向前兼容)。

---

## 9. 与 288 冻结批次的关系

- 本分支在 `par-0901`,**不进 main**,冻结期不合并;
- `parallel.enabled` 默认 **false**;`AGENT_PARALLEL=0` 是无条件硬闸(优先级最高),bench runner 未来也无需改任何东西;
- 即使未来默认开启,bench 侧也用一行环境变量整体关掉;
- 阈值/模型名/并发数全部来自 config,不存在"改行为要改代码"。

## 10. 配置参考(`~/.ollama_agent/config.json` 的 `parallel` 段;环境变量可覆盖)

```jsonc
{
  "parallel": {
    "enabled": false,                  // 总开关(默认关,冻结期安全)
    "child_model": "",                 // 子模型 tag,空=功能关。零硬编码:必须显式配置
    "child_ctx": 8192,                 // 子模型上下文(KV 成本主要杠杆)
    "min_pending_items": 6,            // 触发:未完成条目阈值
    "min_dispatchable": 2,             // 触发:可派条目阈值
    "hard_cap": 2,                     // 并发硬上限
    "ram_utilization_cap": 0.70,
    "ram_reserve_bytes": 1610612736,   // 1.5GB
    "bytes_per_param": 1000000000.0,
    "weight_overhead": 1.25,
    "runtime_overhead_bytes": 858993459,
    "process_overhead_bytes": 214748365,
    "kv_bytes_per_1k_token": {"2.5": 67108864, "4.5": 157286400, "8.0": 262144000},
    "max_child_params_b": 8.0,
    "allow_parent_eviction": false,
    "allow_overwrite_existing": false,
    "per_task_timeout_s": 900,
    "verify_timeout_s": 300,
    "verify_command_enabled": false,   // 可选 verify 命令(默认关;开了也过命令黑名单)
    "max_retries": 1,
    "retry_on_severe": false,          // 严重违规后是否重试(默认不)
    "max_depth": 1,
    "dispatch_dirname": "_dispatch",   // 子任务分区目录名
    "agent_entry": "ollama_agent.py",  // 子进程入口
    "poll_interval_s": 0.5,            // 子进程存活轮询间隔

    // ---- 子 agent 安全模型(出厂默认 = 最严档;规则是数据,不是代码) ----
    "child_allowed_tools": ["read_file", "list_dir", "create_file", "todo", "finish"],
    "child_allow_commands": false,     // 命令工具默认不进子 agent 工具面
    "sensitive_dir_patterns": [],      // workdir 内也有意义的敏感项;空 = 出厂最严默认
    "system_dir_patterns": [],         // 绝对系统位置(审计精确原因);空 = 出厂最严默认
    "core_system_dir_patterns": [],    // workdir 误配进硬系统区的守卫子集;空 = 出厂默认
    "read_allow_patterns": [],         // 敏感路径读白名单(默认空 = 读也拒)
    "dangerous_command_patterns": [],  // 空 = 用出厂最严默认
    "extra_dangerous_command_patterns": [],
    "max_denies_per_child": 3,
    "audit_poll_interval_s": 5.0,

    // ---- 分类器(可追加/精简) ----
    "veto_patterns": ["..."],
    "simple_patterns": ["..."]
  }
}
```

环境变量:`AGENT_PARALLEL=0`(无条件硬闸)、`HUMMINGBIRD_DEPTH`(派发深度)、`AGENT_PARALLEL_MODEL/CTX/MIN_ITEMS/MIN_DISPATCH/MAX/TIMEOUT/DEPTH`(覆盖对应配置)。模型名/阈值/并发数/安全规则没有任何一处写死在逻辑代码里。

## 11. 实现清单与测试

| 模块 | 内容 | 测试 |
|---|---|---|
| `parallel_config.py` | `DEFAULT_PARALLEL` + 深合并 + env 覆盖 + 类型收敛 | 合并/覆盖/非法值回退 |
| `parallel_probe.py` | `ResourceProbe`(内存三级回退 + `/api/ps`)、`estimate_child_cost`、`plan_capacity` | 注入假读数器;公式边界(0 预算/整除边界/共存门/超参数量拒派) |
| `parallel_safety.py` | 归一化、敏感目录四类、危险命令黑名单(severe/deny 分级)、链式拆段、重定向检查、`ChildSandbox`(审计+计数+终止)、审计读取/汇总 | **每一类敏感目录、每一个 severe 命令族、带引号/转义/链式/重定向变体、default-deny 无升级、计数终止** |
| `parallel_todo.py` | `TodoItem`/`TodoProvider`/`JsonTodoProvider`、`classify_task`、`should_dispatch` | 分类器正反例、触发 AND 逻辑、注解不能越过负面清单/安全预检 |
| `parallel_dispatch.py` | `ParallelDispatcher`(spawn 池/超时/中止/审计采样)+ `Integrator`(verify/审计复核/拷回/冲突)+ CLI `plan` | 注入假 spawn_fn:成功/失败/重试/超时/中止/冲突/全失败回退/严重违规不重试 |
| `ollama_agent.py` | child mode 安装(工具面收窄 + 沙箱接入 `_gate_check` + 确认通道短路 + severe exit 53)+ `agent_loop` 顶部派发 hook | mock 全链路,不断言真实模型 |
| `agent_gui.py` | `@@DISPATCH@@` 解析 → 状态栏 + transcript 备注 | 行协议解析单测 |

测试原则:全部 mock,不启动模型、不碰 GPU/ollama 实体;`ResourceProbe`/`Dispatcher` 的外部依赖(内存读数器、HTTP、Popen)都是构造参数注入。

**最终测试结果(worktree 内全量):241 passed, 0 failed**(`D:\Python312\python.exe -m pytest tests/ -q`),其中并行派发新增 5 个测试文件共 186 例:安全模型 100(含带引号/转义/链式变体、AppData 下 workdir 回归、workdir 误配守卫)、探测 19、触发 36、派发与整合 23、配置 8(含"五个模块零模型名硬编码"扫描与 prefill 774 token 基线回归)。另有 55 例为主仓原有测试(test_core/guards/lrabh/manifest),全部不受影响。
