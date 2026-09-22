# -*- coding: utf-8 -*-
r"""
resource_table_2609.py — LRAB-288 的 per-arm / per-tier 资源计量表(纯读,零新实验,可复跑)。

回应审稿 P1 项:全文只报 wall-clock,缺 token / turn / timeout 字段
(DeepSeek §4.10;qwen 3.6 要求 per-arm timeout 格数 + turns/cell + tokens/cell,并按 tier 报)。

输入(全部只读,不修改任何源文件):
  A) <EVAL_ROOT>/mingbird-v16/benchmarks/lrab_scores.csv
     — 主矩阵 288 格:(harness,task,model,score,wall_seconds,latest_attempt_dir)
  B) <EVAL_ROOT>/<HB>/eval_results/<latest_attempt_dir>/
     — Mingbird / agent-mini 臂的 transcript.txt + score.json
  C) <EVAL_ROOT>/mingbird-v150/eval_results/rr_think0/<dir>/
     — goose / opencode 臂(统一协议批)的 transcript.txt + score.json
  D) <EVAL_ROOT>/mingbird-v16/benchmarks/mechanism_log/turns_resource_summary.csv
     — 仅用于交叉校验(不参与计算)

输出(只写本目录 p1_forensics\\):
  - resource_table_2609.csv  — 逐格一行 × 288
  - resource_table_2609.md   — 论文附录用:per-arm 汇总 + per-tier 断面 + 口径与不可得字段

用法:  python resource_table_2609.py
复跑一致性:数值全部现算,脚本内不写死任何结论数字。

------------------------------------------------------------------------------
口径(诚实第一,宁缺勿造)
------------------------------------------------------------------------------
[1] tool_calls —— 按臂各自 transcript 的工具行为行,与
    p1_forensics/turns_resource.csv(extract_p1.py) 完全相同的规则:
      Mingbird   : 正则  \[\d+\|\+\d+s\] ⚙   (逐次工具调用行;实测等价于行内 '⚙' 计数)
      agent-mini : 行首  ⚡ <tool>            (^\s*⚡ \S)
      goose      : 行首  ▸ <tool>             (^\s*▸)
      opencode   : ANSI 剥离后 行首 '$ ' 命令行 或 '→ ' 动作行
    四臂的打印格式互不相同(2026-09-21 各臂各抽 ≥2 份 transcript 实测确认),
    因此跨臂只宜比量级,不宜当作严格同义指标。

[2] turns —— 只有鸣鸟系(Mingbird)有逐轮真值:
      transcript 每轮打印一行 [ctx: N/32768 = P%],该行数 = 该格模型轮数。
      校验:Mingbird 72 格中 71 格的 ctx 行数 == 最大轮号+1;
      唯一例外是 WF09/qwen3.5_4b(该格中途 ollama 掉线,harness 打印了 95..102 号
      退化轮但没有模型响应,故无 ctx 行)——脚本会在 md 里自动列出该例外。
      agent-mini / goose / opencode 的 transcript 无任何逐轮计数器,
      故 turns 列一律 'n/a (not recorded)':不估算(例如不用 tool_calls+1 冒充)。

[3] prompt_tokens_peak —— 只有鸣鸟系有真值:N 取自 Ollama 响应的
      prompt_eval_count(打印侧代码 mingbird-v150/ollama_agent.py L2789-2792),
      峰值 = 该格所有 [ctx:] 行中最大的 N;预算均为 32768(AGENT_CTX 环境变量)。
      生成侧 token(eval_count)在全部 288+72 份 transcript 中 0 出现
      (代码里唯一的 eval_count 打印出口是空响应取证插桩 L2809,本轮 0 触发),
      故不做生成侧列,亦不估算;表内以脚注注明 'n/a (not recorded)'。

[4] timeout —— 判据(命中任一即 yes;脚本按 T1→T2 顺序判定并写返回值):
      T1  score.json(该格实际解析到的 attempt 目录)failure_mode == 'timeout'
      T2  lrab_scores.csv 的 wall_seconds 存在且 >= 该格预算
          预算:WF/tier1-3 = 90min = 5400s;LH/tier4 = 180min = 10800s。
          来源:run_matrix.py 的 --timeout-min / --timeout-min-lh(默认 2x)下发到
          run_bench.py --timeout-min;本批实跑日志可证:
            <HB>/eval_results/logs/matrix_*.log  "WF budget=90min, LH budget=180min"
            rr_think0/logs/matrix_*.log                  "starting (budget 90min|180min)"
      未采用"transcript 字符串即算超时"的粗口径,理由(实测反例,勿再犯):
        - Mingbird 的 "[已超时:300 秒上限,进程树已终止]" 是 run_bash 单条命令的
          300s 上限,不是格子预算超时(4 格出现);
        - goose 的 "Warning: Response reached the model's output-token limit..." 是
          生成侧 token 上限截断(17 格),非 wall 超时 —— 单列为"截断信号";
        - goose/WF07+WF10 qwen3.5_4b 的 transcript 含 106/216 次字面 'timeout',
          全部来自 PowerShell 报错回显(假阳性来源)。
        timeout 后 runner 不再往 transcript 写任何东西(树杀),故字符串口径无增量。

[5] goose/WF08/qwen3.5_4b 的 wall_seconds 在 lrab_scores.csv 中为空 —— 如实保留
    'n/a',不补数(EXCLUSIONS.md:用户裁定该格记 0 分)。

[6] goose / opencode 行的 latest_attempt_dir 是逻辑名(rr_think0_<task>),
    不是目录名;须按 (harness,task,model) 在 rr_think0\ 下用目录名模式
    <harness>_<task>_<model>_m<N>_<MMDD_HHMMSS> 反查,取时间戳最新且含
    transcript.txt 者(最新目录可能是被外部击杀、无 transcript 的空目录)。
    与 extract_p1.py 同规则,故两张表可互相印证。

复跑说明:<EVAL_ROOT> 为本地评测根目录;<HB> 为产出 Mingbird / agent-mini 两臂的
历史工作树目录名,按本机实际情况替换。本仓库只含本目录下的派生表(CSV/MD),
原始 transcript 与 score.json 不在仓库内。
"""
import csv
import os
import re
import statistics
import sys

# ---------------------------------------------------------------- 路径与常量
BASE = r'<EVAL_ROOT>'                     # 本地评测根目录,按需替换
SCORES = os.path.join(BASE, 'mingbird-v16', 'benchmarks', 'lrab_scores.csv')
HB = os.path.join(BASE, '<HB>', 'eval_results')     # 历史工作树: Mingbird / agent-mini 臂
RR = os.path.join(BASE, 'mingbird-v150', 'eval_results', 'rr_think0')  # goose / opencode
OLD_SUMMARY = os.path.join(BASE, 'mingbird-v16', 'benchmarks', 'mechanism_log',
                           'turns_resource_summary.csv')   # 仅交叉校验
OLD_CELLS = os.path.join(BASE, 'mingbird-v16', 'benchmarks', 'mechanism_log',
                         'turns_resource.csv')           # 仅交叉校验
OUT = os.path.dirname(os.path.abspath(__file__))   # 只写本目录

CSV_OUT = os.path.join(OUT, 'resource_table_2609.csv')
MD_OUT = os.path.join(OUT, 'resource_table_2609.md')

ARM_ORDER = ['Mingbird', 'agent-mini', 'goose', 'opencode']
TIER_ORDER = ['2B', '4B', '12B', '35B']
# 模型 slug -> 参数档(与 benchmarks/models.lock 的 4 个 tag 一一对应)
TIER_OF_MODEL = {
    'gemma4_e2b': '2B',        # ollama tag gemma4:e2b
    'qwen3.5_4b': '4B',        # ollama tag qwen3.5:4b
    'gemma4_12b': '12B',       # ollama tag gemma4:12b
    'ornith1.5_35b': '35B',    # ollama tag ornith-1.5:35b
}
# 格子 wall 预算(秒)。证据见文件头 [4]。
BUDGET_WF_S = 90 * 60      # tier1-3 / WF-xx
BUDGET_LH_S = 180 * 60     # tier4_longhorizon / LH-xx

TOK_NA = 'n/a (not recorded)'          # 生成侧 token / 非鸣鸟臂的 token 与 turns
WALL_NA = 'n/a'

# ---------------------------------------------------------------- 计数规则
RE_GEAR = re.compile(r'\[\d+\|\+\d+s\] ⚙')          # Mingbird
RE_AGENTMINI = re.compile(r'^\s*⚡ \S')               # agent-mini
RE_GOOSE = re.compile(r'^\s*▸')                       # goose
RE_OC_CMD = re.compile(r'^\$ ')                       # opencode shell 行
RE_OC_TOOL = re.compile(r'^→ ')                       # opencode 动作行
RE_ANSI = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')
RE_CTX = re.compile(r'\[ctx: (\d+)/(\d+) = (\d+)%\]')  # Mingbird 逐轮 ctx(真值)
RE_TURN_IDX = re.compile(r'^\[(\d+)(?:\|[^\]]*)?\]', re.M)
RE_RR_DIR = re.compile(r'^(goose|opencode)_(LH\d+|WF\d+)_(.+?)_(m\d)_(\d{4}_\d{6})$')
RE_RR_SCAN = RE_RR_DIR
# 鸣鸟主臂/agent-mini 的 attempt 目录名(用于"历史 attempt 曾超时"扫描)
RE_HB_DIR = re.compile(r'^(mingbird|agentmini)_(LH\d+|WF\d+)_(.+?)_(m\d)_(\d{4}_\d{6})$')

# 诊断用 marker(非 timeout,单独列在 md 第 5 节)
MARK_GOOSE_TRUNC = "reached the model's output-token limit"      # goose CLI 生成侧截断
MARK_MB_COMPACT = '超限,已压缩(L'                                  # 鸣鸟 上下文压缩(估算值,非 token 真值)
MARK_MB_CTXTRUNC = '[上下文压缩 L1: 截断旧工具输出]'                # 鸣鸟 旧工具输出截断


def read_text(path):
    with open(path, encoding='utf-8', errors='replace') as f:
        return f.read()


def count_tool_calls(arm, text):
    """按臂的工具行为行计数(规则见文件头 [1];与 extract_p1.py 一致)。"""
    if arm == 'Mingbird':
        return len(RE_GEAR.findall(text))
    if arm == 'agent-mini':
        return sum(1 for ln in text.splitlines() if RE_AGENTMINI.match(ln))
    if arm == 'goose':
        return sum(1 for ln in text.splitlines() if RE_GOOSE.match(ln))
    if arm == 'opencode':
        n = 0
        for ln in text.splitlines():
            ln2 = RE_ANSI.sub('', ln)
            if RE_OC_CMD.match(ln2) or RE_OC_TOOL.match(ln2):
                n += 1
        return n
    raise ValueError(arm)


def is_lh(task):
    return task.startswith('LH')


def budget_of(task):
    return BUDGET_LH_S if is_lh(task) else BUDGET_WF_S


# ---------------------------------------------------------------- 目录解析
def build_rr_index():
    """rr_think0 下按 (harness,task,model) -> [(时间戳, 目录名)] 建索引。"""
    idx = {}
    for d in os.listdir(RR):
        m = RE_RR_DIR.match(d)
        if m and os.path.isdir(os.path.join(RR, d)):
            idx.setdefault((m.group(1), m.group(2), m.group(3)), []).append((m.group(5), d))
    return idx


def resolve_dir(row, rr_idx, quirks):
    """返回该格实际使用的 attempt 目录绝对路径;与 extract_p1.py 同规则。"""
    h, task, model = row['harness'], row['task'], row['model']
    if h in ('Mingbird', 'agent-mini'):
        d = os.path.join(HB, row['latest_attempt_dir'])
        if not os.path.isdir(d):
            quirks.append(f'MISSING DIR {h}/{model}/{task}: {d}')
            return None, ''
        return d, os.path.basename(d)
    cands = sorted(rr_idx.get((h, task, model), []))
    if not cands:
        quirks.append(f'MISSING RR DIR {h}/{model}/{task} (csv name={row["latest_attempt_dir"]})')
        return None, ''
    chosen = next((c for c in reversed(cands)
                   if os.path.exists(os.path.join(RR, c[1], 'transcript.txt'))), cands[-1])
    if len(cands) > 1:
        quirks.append(f'AMBIGUOUS {h}/{model}/{task}: {len(cands)} dirs -> chose {chosen[1]}')
    return os.path.join(RR, chosen[1]), chosen[1]


def scan_all_attempts():
    """扫描两棵树里同 (arm,task,model) 的**全部** attempt 目录的 score.json,
    用于诊断"该格曾有一个 attempt 超时、但发布行是重试后的 attempt"。
    返回 {(arm_norm,task,model): [{dir,attempt,failure_mode,wall_seconds,resume}]}"""
    out = {}
    for d in os.listdir(HB):
        m = RE_HB_DIR.match(d)
        if not m or not os.path.isdir(os.path.join(HB, d)):
            continue
        arm = 'Mingbird' if m.group(1) == 'mingbird' else 'agent-mini'
        out.setdefault((arm, m.group(2), m.group(3)), []).append(
            (m.group(4), d, os.path.join(HB, d)))
    for d in os.listdir(RR):
        m = RE_RR_SCAN.match(d)
        if not m or not os.path.isdir(os.path.join(RR, d)):
            continue
        out.setdefault((m.group(1), m.group(2), m.group(3)), []).append(
            (m.group(4), d, os.path.join(RR, d)))
    for k, v in out.items():
        recs = []
        for attempt, dname, dpath in sorted(v, key=lambda x: x[1]):
            sj = os.path.join(dpath, 'score.json')
            fm = wall = resume = None
            if os.path.exists(sj):
                try:
                    import json
                    s = json.load(open(sj, encoding='utf-8'))
                    fm, wall, resume = s.get('failure_mode'), s.get('wall_seconds'), s.get('resume')
                except Exception:
                    pass
            recs.append(dict(dir=dname, attempt=attempt, failure_mode=fm,
                             wall_seconds=wall, resume=resume))
        out[k] = recs
    return out


def scorejson_of(d):
    if not d:
        return {}
    sj = os.path.join(d, 'score.json')
    if not os.path.exists(sj):
        return {}
    try:
        import json
        return json.load(open(sj, encoding='utf-8'))
    except Exception:
        return {}


# ---------------------------------------------------------------- 统计小工具
def mean_med(vals):
    if not vals:
        return None, None, 0
    return statistics.mean(vals), statistics.median(vals), len(vals)


def fnum(x, nd=1):
    if x is None:
        return 'n/a'
    if isinstance(x, int) or abs(x - round(x)) < 1e-9:
        return str(int(round(x)))
    return f'{x:.{nd}f}'


# ---------------------------------------------------------------- 主流程
def main():
    os.makedirs(OUT, exist_ok=True)
    rows = list(csv.DictReader(open(SCORES, encoding='utf-8-sig')))
    rr_idx = build_rr_index()
    all_attempts = scan_all_attempts()
    quirks = []

    cells = []
    for r in rows:
        arm, task, model = r['harness'], r['task'], r['model']
        d, dname = resolve_dir(r, rr_idx, quirks)
        tp = os.path.join(d, 'transcript.txt') if d else ''
        text = read_text(tp) if (tp and os.path.exists(tp)) else None
        if text is None:
            quirks.append(f'NO TRANSCRIPT {arm}/{model}/{task}')

        tool_calls = count_tool_calls(arm, text) if text is not None else None
        ctx = RE_CTX.findall(text) if text else []
        turns = len(ctx) if (arm == 'Mingbird' and text is not None) else None
        peak = max((int(x[0]) for x in ctx), default=None) if (arm == 'Mingbird' and ctx) else None
        ctx_budget = int(ctx[0][1]) if ctx else None

        # timeout:T1 score.json failure_mode / T2 wall >= 预算
        sj = scorejson_of(d)
        wall_raw = r['wall_seconds'].strip()
        wall = float(wall_raw) if wall_raw else None
        budget = budget_of(task)
        t_src = []
        if sj.get('failure_mode') == 'timeout':
            t_src.append('score.json:failure_mode=timeout')
        if wall is not None and wall >= budget:
            t_src.append(f'wall>={budget}s')
        timeout_flag = 'yes:' + '+'.join(t_src) if t_src else 'no'

        # 诊断(不进 CSV):鸣鸟 ctx 行数 vs 最大轮号;截断/压缩 marker
        idx_max = None
        if text and arm == 'Mingbird':
            ix = [int(x) for x in RE_TURN_IDX.findall(text)]
            if ix:
                idx_max = max(ix)
                if idx_max + 1 != turns:
                    quirks.append(f'CTX/TURN-INDEX GAP {arm}/{model}/{task}: '
                                  f'ctx_lines={turns} max_turn={idx_max} '
                                  f'(退化轮无模型响应)')
        goose_trunc = text.count(MARK_GOOSE_TRUNC) if text else 0
        mb_compact = text.count(MARK_MB_COMPACT) if text else 0
        mb_ctxtrunc = text.count(MARK_MB_CTXTRUNC) if text else 0

        cells.append(dict(
            harness=arm, task=task, model=model, tier=TIER_OF_MODEL[model],
            score=r['score'],
            wall_seconds=wall_raw if wall_raw else WALL_NA,
            wall_num=wall,
            tool_calls='' if tool_calls is None else tool_calls,
            turns='' if turns is None else turns,
            prompt_tokens_peak='' if peak is None else peak,
            timeout_flag=timeout_flag,
            attempt_dir=dname,
            failure_mode=sj.get('failure_mode', ''),
            ctx_budget=ctx_budget, ctx_lines=len(ctx), turn_idx_max=idx_max,
            goose_trunc=goose_trunc, mb_compact=mb_compact, mb_ctxtrunc=mb_ctxtrunc,
            dir_abs=d,
        ))

    # ---------------- CSV(逐格一行,列顺序按审稿要求) ----------------
    cols = ['harness', 'task', 'model', 'tier', 'score', 'wall_seconds', 'tool_calls',
            'turns', 'prompt_tokens_peak', 'timeout_flag', 'attempt_dir']
    with open(CSV_OUT, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(cols)
        for c in cells:
            na_turn = c['turns'] if c['turns'] != '' else TOK_NA
            na_tok = c['prompt_tokens_peak'] if c['prompt_tokens_peak'] != '' else TOK_NA
            tc = c['tool_calls'] if c['tool_calls'] != '' else TOK_NA
            w.writerow([c['harness'], c['task'], c['model'], c['tier'], c['score'],
                        c['wall_seconds'], tc, na_turn, na_tok, c['timeout_flag'],
                        c['attempt_dir']])

    # ---------------- 聚合 ----------------
    def agg(sub):
        win = [x['wall_num'] for x in sub if x['wall_num'] is not None]
        tcv = [x['tool_calls'] for x in sub if x['tool_calls'] != '']
        tuv = [x['turns'] for x in sub if x['turns'] != '']
        pkv = [x['prompt_tokens_peak'] for x in sub if x['prompt_tokens_peak'] != '']
        nto = sum(1 for x in sub if x['timeout_flag'].startswith('yes'))
        return dict(cells=len(sub), n_wall=len(win),
                    wall_mean=statistics.mean(win) if win else None,
                    wall_med=statistics.median(win) if win else None,
                    tc_mean=statistics.mean(tcv) if tcv else None,
                    tc_med=statistics.median(tcv) if tcv else None,
                    n_tc=len(tcv),
                    turns_mean=statistics.mean(tuv) if tuv else None,
                    n_turns=len(tuv),
                    peak_med=statistics.median(pkv) if pkv else None,
                    n_peak=len(pkv),
                    timeouts=nto)

    per_arm = {a: agg([c for c in cells if c['harness'] == a]) for a in ARM_ORDER}
    per_tier_arm = {(t, a): agg([c for c in cells if c['tier'] == t and c['harness'] == a])
                    for t in TIER_ORDER for a in ARM_ORDER}
    per_tier = {t: agg([c for c in cells if c['tier'] == t]) for t in TIER_ORDER}

    # ---------------- 交叉校验 turns_resource_summary.csv ----------------
    xcheck = []
    if os.path.exists(OLD_SUMMARY):
        old = {r['harness']: r for r in csv.DictReader(open(OLD_SUMMARY, encoding='utf-8-sig'))}
        for a in ARM_ORDER:
            o = old.get(a)
            if not o:
                xcheck.append((a, 'MISSING in old summary', '', ''))
                continue
            tcv = [c['tool_calls'] for c in cells if c['harness'] == a and c['tool_calls'] != '']
            for label, mine, theirs in (
                    ('cells', len(tcv), int(o['cells'])),
                    ('tool_calls_mean', round(statistics.mean(tcv), 1), float(o['tool_calls_mean'])),
                    ('tool_calls_median', statistics.median(tcv), float(o['tool_calls_median'])),
                    ('min', min(tcv), int(o['min'])),
                    ('max', max(tcv), int(o['max']))):
                ok = (mine == theirs) if isinstance(theirs, int) else (abs(mine - theirs) < 0.05)
                xcheck.append((a, label, mine, theirs, ok))

    # 逐格对照(比 summary 更强的校验:均值可能互相掩盖)
    xcell = []
    if os.path.exists(OLD_CELLS):
        old_cells = {(r['harness'], r['model'], r['task']): r
                     for r in csv.DictReader(open(OLD_CELLS, encoding='utf-8-sig'))}
        for c in cells:
            o = old_cells.get((c['harness'], c['model'], c['task']))
            if not o:
                xcell.append((c['harness'], c['task'], c['model'], 'MISSING', '', ''))
                continue
            pairs = [('tool_calls', str(c['tool_calls']), o['tool_calls']),
                     ('attempt_dir', c['attempt_dir'], o['attempt_dir'])]
            if c['harness'] == 'Mingbird':
                pairs += [('turns(ctx_lines)', str(c['turns']), o['ctx_lines']),
                          ('prompt_tokens_peak', str(c['prompt_tokens_peak']),
                           o['ctx_peak_tokens'])]
            for field, mine, theirs in pairs:
                if mine != theirs:
                    xcell.append((c['harness'], c['task'], c['model'], field, mine, theirs))

    # ---------------- 诊断 ----------------
    # 历史 attempt 曾超时的格(含被重试覆盖者)
    hist_to = []
    for k, recs in sorted(all_attempts.items()):
        to = [x for x in recs if x['failure_mode'] == 'timeout']
        if to:
            pub = next((c for c in cells
                        if (c['harness'], c['task'], c['model']) == k), None)
            hist_to.append(dict(arm=k[0], task=k[1], model=k[2],
                                n_attempts=len(recs), n_timeout_attempts=len(to),
                                published_dir=pub['attempt_dir'] if pub else '',
                                published_is_timeout=(pub['timeout_flag'].startswith('yes')
                                                      if pub else None),
                                timeout_dirs=[x['dir'] for x in to],
                                walls=[x['wall_seconds'] for x in to]))
    trunc_goose = [(c['task'], c['model'], c['goose_trunc']) for c in cells if c['goose_trunc']]
    compact_mb = [(c['task'], c['model'], c['mb_compact'], c['mb_ctxtrunc'])
                  for c in cells if c['mb_compact'] or c['mb_ctxtrunc']]
    n_compact_cells = sum(1 for c in cells if c['mb_compact'])
    n_compact_events = sum(c['mb_compact'] for c in cells)
    n_ctxtrunc_cells = sum(1 for c in cells if c['mb_ctxtrunc'])
    n_ctxtrunc_events = sum(c['mb_ctxtrunc'] for c in cells)
    # 口径对照:若把所有历史 attempt 目录(含被重试覆盖者)都算上,计数会变吗?
    import glob as _glob
    all_dirs = {'A': 0, 'B': 0}
    for tp in _glob.glob(os.path.join(HB, 'mingbird_*', 'transcript.txt')):
        t = read_text(tp)
        if MARK_MB_COMPACT in t:
            all_dirs['A'] += 1
        if MARK_MB_CTXTRUNC in t:
            all_dirs['B'] += 1
    ceiling = [(c['task'], c['model'], c['prompt_tokens_peak'], c['ctx_budget'])
               for c in cells if c['prompt_tokens_peak'] != '' and c['ctx_budget']
               and c['prompt_tokens_peak'] >= c['ctx_budget'] - 1]
    fm_dist = {}
    for c in cells:
        fm_dist.setdefault(c['harness'], {}).setdefault(c['failure_mode'] or 'n/a', 0)
        fm_dist[c['harness']][c['failure_mode'] or 'n/a'] += 1

    # ---------------- MD ----------------
    L = []
    A = L.append
    A('# per-arm 资源计量表 — LRAB-288(2026-09-21 取证,零新实验)')
    A('')
    A('生成脚本:`diagnosis/p1_forensics/resource_table_2609.py`(同目录,`python resource_table_2609.py` 可复跑);'
      '逐格数据:`resource_table_2609.csv`(288 行)。')
    A('')
    A('数据源(只读):`mingbird-v16/benchmarks/lrab_scores.csv`(288 格 = 4 臂 × 4 模型 × 18 任务)、'
      '`<HB>/eval_results/<attempt_dir>/`(Mingbird、agent-mini 臂)、'
      '`mingbird-v150/eval_results/rr_think0/<attempt_dir>/`(goose、opencode 臂)。未修改任何源文件。')
    A('')
    A('## 0 口径(先读这一节再看数字)')
    A('')
    A('| 项 | 口径 |')
    A('|---|---|')
    A('| tool_calls | 各臂自己的工具行为行(正则见脚本头 [1]):Mingbird `[N\\|+Xs] ⚙`、'
      'agent-mini `⚡ <tool>`、goose `▸ <tool>`、opencode(ANSI 剥离后)`$ 命令` + `→ 动作`。'
      '四臂打印格式不同,**跨臂只宜比量级**。 |')
    A('| turns | 仅 Mingbird 有真值 = 逐轮 `[ctx: N/32768 = P%]` 行数(每轮一行,含无工具调用的轮)。'
      'agent-mini / goose / opencode 无任何逐轮计数器 → `n/a (not recorded)`,不估算。 |')
    A(f'| prompt_tokens_peak | 仅 Mingbird 有真值 = 该格 `[ctx: N/…]` 的最大 N;N 取自 Ollama 响应的 '
      f'`prompt_eval_count`(打印侧 `mingbird-v150/ollama_agent.py` L2789-2792)。其余三臂 → `{TOK_NA}`。 |')
    A(f'| 生成侧 token(eval_count) | **全 360 份 transcript 中 0 出现**(唯一打印出口 L2809 本轮 0 触发)'
      f' → 全表 `{TOK_NA}`,不估算。 |')
    A(f'| timeout | T1 `score.json.failure_mode == "timeout"`,或 T2 `wall_seconds >= 预算`'
      f'(WF/tier1-3 = {BUDGET_WF_S}s=90min,LH/tier4 = {BUDGET_LH_S}s=180min;预算由 run_matrix.py '
      f'`--timeout-min`/`--timeout-min-lh` 下发,本批日志明示 "WF budget=90min, LH budget=180min")。'
      f'timeout 列写 `yes:<命中判据>` / `no`。 |')
    A('| wall_seconds | 直接取 `lrab_scores.csv`;goose/WF08/qwen3.5_4b 一格在源 CSV 缺失 → 保留 `n/a`,不补数。 |')
    A('| 未采用的粗口径 | "transcript 里出现 timeout 字样即算超时" 会假阳性:Mingbird 的 '
      '`[已超时:300 秒上限]` 是**单条命令** 300s 上限(4 格)、goose 的 output-token limit 警告是'
      '**生成侧截断**(17 格)、goose/WF07+WF10 qwen 的 106/216 次 `timeout` 全来自 PowerShell 报错回显。 |')
    A('')

    A('## 1 per-arm 汇总(每臂 72 格 = 4 模型 × 18 任务)')
    A('')
    A('| arm | cells | wall mean (s) | wall median (s) | tool_calls mean | tool_calls median | turns mean | prompt 峰值 median | timeout 格数 |')
    A('|---|---|---|---|---|---|---|---|---|')
    for a in ARM_ORDER:
        g = per_arm[a]
        A(f"| {a} | {g['cells']} | {fnum(g['wall_mean'])} (n={g['n_wall']}) | {fnum(g['wall_med'])} | "
          f"{fnum(g['tc_mean'])} (n={g['n_tc']}) | {fnum(g['tc_med'])} | "
          f"{fnum(g['turns_mean']) if g['n_turns'] else TOK_NA} | "
          f"{fnum(g['peak_med'],0) if g['n_peak'] else TOK_NA} | {g['timeouts']} |")
    A('')
    A('注:wall 的统计基数 = 有 wall 值的格;goose 少 1 格(WF08/qwen3.5_4b,源 CSV 缺失)。')
    A('turns / prompt 峰值只有 Mingbird 有值,故其余三臂该两列为 `n/a`。')
    A('')

    A('## 2 per-tier 断面(2B/4B/12B/35B × 各臂;每格 18 cells)')
    A('')
    A('| tier | arm | cells | wall mean (s) | wall median (s) | tool_calls mean | tool_calls median | turns mean | prompt 峰值 median | timeout 格数 |')
    A('|---|---|---|---|---|---|---|---|---|---|')
    for t in TIER_ORDER:
        for a in ARM_ORDER:
            g = per_tier_arm[(t, a)]
            if not g['cells']:
                continue
            A(f"| {t} | {a} | {g['cells']} | {fnum(g['wall_mean'])} (n={g['n_wall']}) | {fnum(g['wall_med'])} | "
              f"{fnum(g['tc_mean'])} | {fnum(g['tc_med'])} | "
              f"{fnum(g['turns_mean']) if g['n_turns'] else TOK_NA} | "
              f"{fnum(g['peak_med'],0) if g['n_peak'] else TOK_NA} | {g['timeouts']} |")
        g = per_tier[t]
        A(f"| **{t} 合计** | 全臂 | {g['cells']} | {fnum(g['wall_mean'])} (n={g['n_wall']}) | {fnum(g['wall_med'])} | "
          f"{fnum(g['tc_mean'])} | {fnum(g['tc_med'])} | "
          f"{fnum(g['turns_mean']) if g['n_turns'] else TOK_NA} | "
          f"{fnum(g['peak_med'],0) if g['n_peak'] else TOK_NA} | {g['timeouts']} |")
    A('')

    A('## 3 字段可得性清单(不可得 = 不估算)')
    A('')
    A('| 字段 | Mingbird | agent-mini | goose | opencode | 说明 |')
    A('|---|---|---|---|---|---|')
    A(f"| wall_seconds | ✓ 72 | ✓ 72 | ✓ 71 + 1 n/a | ✓ 72 | goose WF08/qwen3.5_4b 源 CSV 缺失 |")
    A(f"| tool_calls | ✓ 72 | ✓ 72 | ✓ 72(1 格 0,因 0 字节 transcript) | ✓ 72 | 各臂口径不同 |")
    A(f"| turns | ✓ 72 | {TOK_NA} | {TOK_NA} | {TOK_NA} | 只有鸣鸟逐轮打印 ctx 行 |")
    A(f"| prompt tokens(峰值/逐轮) | ✓ 72 | {TOK_NA} | {TOK_NA} | {TOK_NA} | 三臂未采 prompt_eval_count |")
    A(f"| 生成侧 token(eval_count) | {TOK_NA} | {TOK_NA} | {TOK_NA} | {TOK_NA} | 任何 transcript 中 0 出现 |")
    A(f"| 逐格 exit_code / failure_mode | ✓ | ✓ | ✓ | ✓ | 来自各格 `score.json`(见第 5 节) |")
    A('')
    A('要让四臂 token 可比,需在 runner 层捕获 `/api/chat` 的 `prompt_eval_count`/`eval_count`'
      '(属新实验,不在本次取证范围)。')
    A('')

    A('## 4 与 `mechanism_log/turns_resource_summary.csv` 的交叉校验')
    A('')
    n_cell_cmp = len(cells) * 2 + sum(2 for c in cells if c['harness'] == 'Mingbird')
    if xcheck:
        bad = [x for x in xcheck if len(x) == 5 and not x[4]]
        A(f'**逐格对照**(比 summary 更强:`turns_resource.csv` 288 格 × '
          f'{{tool_calls, attempt_dir}} ∪ 鸣鸟 72 格 × {{turns, prompt 峰值}} = {n_cell_cmp} 项):'
          f'**不一致 {len(xcell)} 项**。')
        if xcell:
            A('')
            A('| arm | task | model | 字段 | 本表 | turns_resource.csv |')
            A('|---|---|---|---|---|---|')
            for x in xcell:
                A(f'| {x[0]} | {x[1]} | {x[2]} | {x[3]} | {x[4]} | {x[5]} |')
        A('')
        A(f'**逐臂汇总对照**(cells / tool_calls mean·median / min / max):'
          f'**共 {len(xcheck)} 项,不一致 {len(bad)} 项**。')
        A('')
        A('| arm | 字段 | 本表 | turns_resource_summary.csv | 一致 |')
        A('|---|---|---|---|---|')
        for x in xcheck:
            if len(x) == 5:
                A(f'| {x[0]} | {x[1]} | {x[2]} | {x[3]} | {"✓" if x[4] else "✗"} |')
            else:
                A(f'| {x[0]} | {x[1]} | {x[2]} | {x[3]} | ✗ |')
    A('')

    A('## 5 资源相关诊断(非 timeout 但有预算压力)')
    A('')
    A('**5.1 failure_mode 分布(各格实际解析到的 attempt 的 score.json)**')
    A('')
    A('| arm | ' + ' | '.join(sorted({k for v in fm_dist.values() for k in v})) + ' |')
    A('|---' * (1 + len(sorted({k for v in fm_dist.values() for k in v}))) + '|')
    modes = sorted({k for v in fm_dist.values() for k in v})
    for a in ARM_ORDER:
        A(f"| {a} | " + ' | '.join(str(fm_dist[a].get(m, 0)) for m in modes) + ' |')
    A('')
    A('**5.2 历史 attempt 曾超时的格(含被重试覆盖、发布行非超时的情形)**')
    A('')
    if hist_to:
        A('| arm | task | model | attempts | 超时 attempts | 超时 attempt 目录 | 该 attempt wall (s) | 发布行是否 timeout |')
        A('|---|---|---|---|---|---|---|---|')
        for h in hist_to:
            A(f"| {h['arm']} | {h['task']} | {h['model']} | {h['n_attempts']} | "
              f"{h['n_timeout_attempts']} | {', '.join(h['timeout_dirs'])} | "
              f"{', '.join(str(x) for x in h['walls'])} | "
              f"{'yes' if h['published_is_timeout'] else 'no(重试后被覆盖)'} |")
    else:
        A('(无)')
    A('')
    A(f"**5.3 生成侧截断信号(goose CLI)** — `{MARK_GOOSE_TRUNC}`:{len(trunc_goose)} 格")
    A('')
    if trunc_goose:
        A('| task | model | 次数 |')
        A('|---|---|---|')
        for t, m, n in trunc_goose:
            A(f'| {t} | {m} | {n} |')
    A('')
    A('**5.4 鸣鸟上下文预算事件(两类,勿混为一谈)**')
    A('')
    A(f"- A 类 = 事前估算超限后压缩 `{MARK_MB_COMPACT}…`:"
      f"**{n_compact_cells} 格 / {n_compact_events} 次**。触发文案里的 token 数是本地启发式"
      f"`_estimate_messages_tokens` 的**估算值**,不是 Ollama 真值,只能当事件计数用。")
    A(f"- B 类 = 旧工具输出截断 `{MARK_MB_CTXTRUNC}`:"
      f"**{n_ctxtrunc_cells} 格 / {n_ctxtrunc_events} 次**(不涉及 token 计数,纯上下文策略事件)。")
    A('')
    A(f"口径提示:以上只统计 288 个发布格所解析到的 attempt(与 `turns_resource.csv` 同口径)。"
      f"若把 `<HB>/eval_results/` 下全部历史 attempt 目录(含被重试覆盖者)都算,"
      f"A 类 {all_dirs['A']} 个目录、B 类 {all_dirs['B']} 个目录"
      f"(多出的目录是未进入发布矩阵的旧 attempt,勿与发布口径混用)。")
    A('')
    if compact_mb:
        A('| task | model | A 类:压缩(L1/L2/L3) | B 类:L1 旧工具输出截断 |')
        A('|---|---|---|---|')
        for t, m, n1, n2 in compact_mb:
            A(f'| {t} | {m} | {n1} | {n2} |')
    A('')
    A(f'**5.5 鸣鸟 prompt 峰值触及 ctx 预算({32768} 天花板)** — {len(ceiling)} 格')
    A('')
    if ceiling:
        A('| task | model | prompt 峰值 | 预算 |')
        A('|---|---|---|---|')
        for t, m, p, b in ceiling:
            A(f'| {t} | {m} | {p} | {b} |')
    A('')
    A('## 6 数据坑(复跑时勿踩)')
    A('')
    A('1. goose/opencode 行的 `latest_attempt_dir` 是逻辑名 `rr_think0_<task>`,不是目录名;'
      '须按 (harness,task,model) 在 `rr_think0/` 反查实际目录,取时间戳最新且**含 transcript.txt** 者。')
    A('2. goose/WF08/qwen3.5_4b 有 4 个 attempt 目录(m0×2 均 90min 超时;m1×2 被外部击杀、'
      '无 transcript 无 score.json)→ 解析回退到 m0_0918_164743(0 字节 transcript,tool_calls=0);'
      '发布行 wall 为空,本表保留 `n/a`。')
    A('3. Mingbird/WF09/qwen3.5_4b 发布行是 failure_mode=error 的重试 attempt(1043.7s);'
      '同格更早 attempt(5400.7s)是 90min 超时(见 5.2)。')
    A('4. `score.json` 与 matrix 运行日志均无 token 字段(见 mechanism_log/tokens_probe.md)。')
    A('5. 鸣鸟的 ctx 行数在 71/72 格等于最大轮号+1;唯一例外 WF09/qwen3.5_4b 是掉线格'
      '(退化轮无模型响应,不打印 ctx 行)。')
    if quirks:
        A('')
        A('### 解析告警(自动生成)')
        A('')
        for q in quirks:
            A(f'- {q}')
    A('')
    with open(MD_OUT, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(L))

    # ---------------- 控制台摘要 ----------------
    print(f'cells={len(cells)}  csv -> {CSV_OUT}')
    print(f'md  -> {MD_OUT}')
    for a in ARM_ORDER:
        g = per_arm[a]
        print(f"  {a:10s} wall_mean={fnum(g['wall_mean'])} median={fnum(g['wall_med'])} "
              f"tc_mean={fnum(g['tc_mean'])} turns_mean={fnum(g['turns_mean'])} "
              f"peak_med={fnum(g['peak_med'],0)} timeouts={g['timeouts']}")
    bad = [x for x in xcheck if len(x) == 5 and not x[4]]
    print(f'xcheck per-cell ({n_cell_cmp} items) vs turns_resource.csv: {len(xcell)} mismatched')
    for x in xcell:
        print('   CELL MISMATCH', x)
    print(f'xcheck per-arm summary vs turns_resource_summary.csv: {len(xcheck)} items, {len(bad)} mismatched')
    for x in bad:
        print('   MISMATCH', x)
    print(f'historical-timeout cells={len(hist_to)}; goose truncated cells={len(trunc_goose)}; '
          f'mingbird compaction {n_compact_cells} cells/{n_compact_events} events; '
          f'L1 tool-output truncation {n_ctxtrunc_cells} cells/{n_ctxtrunc_events} events; '
          f'ctx-ceiling cells={len(ceiling)}')
    print(f'quirks={len(quirks)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
