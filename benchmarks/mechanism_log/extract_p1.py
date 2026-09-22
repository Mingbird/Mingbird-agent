# -*- coding: utf-8 -*-
"""
P1 取证提取:从本地评测 transcript 提取三张表(零新实验,纯读)。
输入(只读):
  - <EVAL_ROOT>\\mingbird-v16\\benchmarks\\lrab_scores.csv  (主矩阵 288 格)
  - <EVAL_ROOT>\\<HB>\\eval_results\\<dir>\\transcript.txt        (Mingbird / agent-mini)
  - <EVAL_ROOT>\\mingbird-v150\\eval_results\\rr_think0\\<dir>\\transcript.txt (goose / opencode)
  - <EVAL_ROOT>\\mingbird-v150\\eval_results\\ablation\\{finish_gate,verify_feedback,anti_loop,flat_prefill}\\<dir>\\transcript.txt
输出(只写 p1_forensics\\):
  - mechanism_activation.csv (+ mechanism_activation_summary.csv)
  - turns_resource.csv (+ turns_resource_summary.csv)
  - tokens_probe_data.json (供 tokens_probe.md 引用)
用法: python extract_p1.py [--sample]
"""
import csv, json, os, re, statistics, sys

BASE = r'<EVAL_ROOT>'  # 本地评测根目录,按需替换
SCORES = BASE + r'\mingbird-v16\benchmarks\lrab_scores.csv'
HB = os.path.join(BASE, '<HB>', 'eval_results')   # 历史工作树(本地归档,不在公开面分发)
LEGACY_PREFIX = '<legacy_prefix>'  # 该树结果目录名前缀,仅用于解析本地归档
RR = BASE + r'\mingbird-v150\eval_results\rr_think0'
ABL = BASE + r'\mingbird-v150\eval_results\ablation'
OUT = BASE + r'\mingbird-release\diagnosis\p1_forensics'

SAMPLE = '--sample' in sys.argv

# ---------------- 机制 marker 定义 ----------------
# 文案以 ollama_agent.py(mingbird-v150)打印语句 + transcript 实际词汇表双重确认。
# family: finish_gate / anti_loop / format_rescue / plan_nudge / edit_guard / budget_nudge
MARKERS = [
    # key,                     中文文案(计数用子串),        family
    ('fake_finish_reject',     '拒绝假 finish',              'finish_gate'),
    ('tests_failed_reject',    '测试未通过',                 'finish_gate'),
    ('artifact_missing_reject','产物核对:summary 声称但缺失','finish_gate'),
    ('plan_missing_reject',    '计划核对:计划点名但缺失',    'finish_gate'),
    ('plan_unsynced_reject',   '计划未同步',                 'finish_gate'),
    ('selfcheck_reinject',     '交付自查:回注任务原文',      'finish_gate'),
    ('dup_call_intercept',     '重复调用拦截',               'anti_loop'),
    ('disabled_tool_hard_reset','被禁用后仍被调用',           'anti_loop'),
    ('empty_turns_hard_reset', '连续空轮×',                  'anti_loop'),
    ('empty_graceful_exit',    '个空轮且 3 次复位无效',      'anti_loop'),
    ('repeat_output_detected', '检测到重复输出',             'anti_loop'),
    ('qa_guard_intercept',     '问答守护:拦截',              'anti_loop'),
    ('force_finish_loop_guard','本轮已足够,强制结束',        'anti_loop'),
    ('break_500_loop_inject',  '500 错误,已注入继续提示',    'anti_loop'),
    ('len_trunc_signature',    'done_reason=length 且无正文无调用', 'anti_loop'),
    ('salvage_text_toolcall',  '抢救到文本工具调用',         'format_rescue'),
    ('alias_mapping',          '别名映射:',                  'format_rescue'),
    ('repair_conversation',    '修复对话结构',               'format_rescue'),
    ('plan_stall_nudge',       '计划停滞提醒',               'plan_nudge'),
    ('shotgun_edit_warn',      '霰弹枪编辑提示',             'edit_guard'),
    ('budget_nudge_inject',    '预算提示已注入',             'budget_nudge'),
]

# ---------------- tool-call 计数口径(按臂) ----------------
RE_GEAR = re.compile(r'\[\d+\|\+\d+s\] ⚙')          # Mingbird / ablation
RE_AGENTMINI = re.compile(r'^\s*⚡ \S')               # agent-mini
RE_GOOSE = re.compile(r'^\s*▸')                       # goose
RE_OC_CMD = re.compile(r'^\$ ')                       # opencode: shell 命令行
RE_OC_TOOL = re.compile(r'^→ ')                       # opencode: 工具动作行
RE_ANSI = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')
RE_CTX = re.compile(r'\[ctx: (\d+)/(\d+) = (\d+)%\]')

def read_text(p):
    with open(p, encoding='utf-8', errors='replace') as f:
        return f.read()

def count_tool_calls(arm, text):
    if arm in ('Mingbird', 'ablation'):
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

# ---------------- 目录解析 ----------------
def resolve_cells():
    rows = list(csv.DictReader(open(SCORES, encoding='utf-8-sig')))
    assert len(rows) == 288
    cells = []
    quirks = []
    # rr 臂: 实际目录 <harness>_<task>_<model>_<m0|m1>_<ts>;CSV 里是逻辑名 rr_think0_<task>
    rr_dirs = {}
    pat = re.compile(r'^(goose|opencode)_(LH\d+|WF\d+)_(.+?)_(m\d)_(\d{4}_\d{6})$')
    for d in os.listdir(RR):
        m = pat.match(d)
        if m and os.path.isdir(os.path.join(RR, d)):
            rr_dirs.setdefault((m.group(1), m.group(2), m.group(3)), []).append((m.group(5), d))
    for r in rows:
        h, model, task = r['harness'], r['model'], r['task']
        if h in ('Mingbird', 'agent-mini'):
            d = os.path.join(HB, r['latest_attempt_dir'])
            if not os.path.isdir(d):
                quirks.append(f'MISSING DIR {h}/{model}/{task}: {d}')
                continue
        else:
            cands = sorted(rr_dirs.get((h, task, model), []))
            if not cands:
                quirks.append(f'MISSING RR DIR {h}/{model}/{task} (csv says {r["latest_attempt_dir"]})')
                continue
            if len(cands) > 1:
                quirks.append(f'AMBIGUOUS {h}/{model}/{task}: {len(cands)} dirs {[c[1] for c in cands]}')
            # 优先取最新且存在 transcript.txt 的目录(最新目录可能被外部击杀、无 transcript)
            chosen = next((c for c in reversed(cands)
                           if os.path.exists(os.path.join(RR, c[1], 'transcript.txt'))), cands[-1])
            if len(cands) > 1:
                quirks.append(f'RESOLVED {h}/{model}/{task} -> {chosen[1]} (最新无 transcript 时回退到最新含 transcript 的目录)')
            d = os.path.join(RR, chosen[1])
            tp = os.path.join(d, 'transcript.txt')
            if os.path.exists(tp) and os.path.getsize(tp) == 0:
                quirks.append(f'EMPTY TRANSCRIPT {h}/{model}/{task} -> {chosen[1]} (0 bytes)')
        t = os.path.join(d, 'transcript.txt')
        cells.append(dict(harness=h, model=model, task=task,
                          score=r['score'], wall=r['wall_seconds'],
                          attempt_dir=os.path.basename(d), transcript=t))
    return cells, quirks

def resolve_ablation():
    cells = []
    quirks = []
    for variant in ('finish_gate', 'verify_feedback', 'anti_loop', 'flat_prefill'):
        vd = os.path.join(ABL, variant)
        pat = re.compile(r'^' + re.escape(LEGACY_PREFIX) + r'_([A-Z]+\d+?)_(.+?)_m\d_\d{4}_\d{6}$')
        for d in sorted(os.listdir(vd)):
            m = pat.match(d)
            full = os.path.join(vd, d)
            if not m or not os.path.isdir(full):
                continue
            t = os.path.join(full, 'transcript.txt')
            if not os.path.exists(t):
                quirks.append(f'ABL NO TRANSCRIPT {variant}/{d}')
                continue
            cells.append(dict(harness=f'ablation:{variant}', model=m.group(2), task=m.group(1),
                              score='', wall='', attempt_dir=d, transcript=t))
    return cells, quirks

# ---------------- 主流程 ----------------
def main():
    os.makedirs(OUT, exist_ok=True)
    main_cells, q1 = resolve_cells()
    abl_cells, q2 = resolve_ablation()
    quirks = q1 + q2

    if SAMPLE:
        pick = []
        for want in [('Mingbird', 'gemma4_12b', 'LH01'), ('goose', 'gemma4_12b', 'LH01'),
                     ('opencode', 'ornith1.5_35b', 'LH02'), ('agent-mini', 'gemma4_12b', 'LH01')]:
            for c in main_cells:
                if (c['harness'], c['model'], c['task']) == want:
                    pick.append(c); break
        for c in pick:
            text = read_text(c['transcript'])
            tc = count_tool_calls(c['harness'], text)
            ctx = RE_CTX.findall(text)
            mk = {k: text.count(zh) for k, zh, _ in MARKERS}
            print(f"{c['harness']}/{c['model']}/{c['task']} dir={c['attempt_dir']}")
            print(f"  tool_calls={tc}  ctx_lines={len(ctx)}"
                  + (f" ctx_first={ctx[0][0]} ctx_peak={max(int(x[0]) for x in ctx)}" if ctx else ''))
            active = {k: v for k, v in mk.items() if v}
            print(f"  markers={active if active else '{}'}")
        print('quirks:', quirks)
        return

    # ---- 表1: mechanism_activation ----
    mech_rows = []
    fam_tot = {}   # (arm, model, family) -> total
    marker_tot = {}
    arm_of = lambda c: c['harness']
    for c in main_cells + abl_cells:
        if not (c['harness'] == 'Mingbird' or c['harness'].startswith('ablation:')):
            continue
        text = read_text(c['transcript'])
        arm = arm_of(c)
        for key, zh, fam in MARKERS:
            n = text.count(zh)
            mech_rows.append(dict(harness=arm, model=c['model'], task=c['task'],
                                  marker=key, marker_zh=zh, count=n))
            fam_tot[(arm, c['model'], fam)] = fam_tot.get((arm, c['model'], fam), 0) + n
            marker_tot[(arm, c['model'], key)] = marker_tot.get((arm, c['model'], key), 0) + n
    with open(os.path.join(OUT, 'mechanism_activation.csv'), 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['harness', 'model', 'task', 'marker', 'marker_zh', 'count'])
        w.writeheader(); w.writerows(mech_rows)
    with open(os.path.join(OUT, 'mechanism_activation_summary.csv'), 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(['harness(arm)', 'model', 'family', 'marker', 'marker_zh', 'total_triggers'])
        fam_of = {k: fam for k, zh, fam in MARKERS}
        zh_of = {k: zh for k, zh, fam in MARKERS}
        for (arm, model, key), v in sorted(marker_tot.items()):
            w.writerow([arm, model, fam_of[key], key, zh_of[key], v])

    # ---- 表2: turns_resource ----
    tr_rows = []
    per_arm_vals = {}
    ctx_stats = []
    for c in main_cells:
        if not os.path.exists(c['transcript']):
            tr_rows.append(dict(harness=c['harness'], model=c['model'], task=c['task'],
                                tool_calls='', attempt_dir=c['attempt_dir'], method='TRANSCRIPT MISSING',
                                note='', ctx_lines='', ctx_peak_tokens=''))
            quirks.append(f"NO TRANSCRIPT {c['harness']}/{c['model']}/{c['task']}")
            continue
        text = read_text(c['transcript'])
        tc = count_tool_calls(c['harness'], text)
        method = {'Mingbird': r'[\d|\+s] ⚙ 行', 'agent-mini': '⚡ 工具行',
                  'goose': '▸ 工具行', 'opencode': '$ 命令行 + → 动作行(ANSI 剥离)'}[c['harness']]
        note = ''
        if os.path.getsize(c['transcript']) == 0:
            note = 'transcript 为 0 字节(超时被杀,无任何日志)'
        ctx = RE_CTX.findall(text)
        ctx_n = len(ctx); ctx_peak = max((int(x[0]) for x in ctx), default=None)
        if c['harness'] == 'Mingbird':
            note = f'ctx预算={ctx[0][1]}' if ctx else '无ctx行'
        tr_rows.append(dict(harness=c['harness'], model=c['model'], task=c['task'], tool_calls=tc,
                            attempt_dir=c['attempt_dir'], method=method, note=note,
                            ctx_lines=ctx_n, ctx_peak_tokens=ctx_peak if ctx_peak is not None else ''))
        per_arm_vals.setdefault(c['harness'], []).append(tc)
        if ctx:
            ctx_stats.append(dict(harness=c['harness'], model=c['model'], task=c['task'],
                                  ctx_lines=ctx_n, ctx_peak=ctx_peak, ctx_budget=int(ctx[0][1])))
    with open(os.path.join(OUT, 'turns_resource.csv'), 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['harness', 'model', 'task', 'tool_calls', 'attempt_dir',
                                          'method', 'note', 'ctx_lines', 'ctx_peak_tokens'])
        w.writeheader(); w.writerows(tr_rows)
    with open(os.path.join(OUT, 'turns_resource_summary.csv'), 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(['harness', 'cells', 'tool_calls_mean', 'tool_calls_median', 'min', 'max'])
        for arm, vals in sorted(per_arm_vals.items()):
            w.writerow([arm, len(vals), round(statistics.mean(vals), 1),
                        statistics.median(vals), min(vals), max(vals)])

    # ---- 表3 数据: tokens probe ----
    probe = dict(quirks=quirks, ctx_stats=ctx_stats)
    # 1) 全 288 + 消融 transcript 里 token 字样覆盖
    tok_cover = {}
    for c in main_cells + abl_cells:
        if not os.path.exists(c['transcript']):
            continue
        text = read_text(c['transcript'])
        arm = c['harness'] if not c['harness'].startswith('ablation:') else 'ablation'
        e = tok_cover.setdefault(arm, dict(files=0, with_ctx=0, with_eval_count_str=0, with_token_word=0))
        e['files'] += 1
        if RE_CTX.search(text): e['with_ctx'] += 1
        if 'eval_count' in text or re.search(r'eval=\d+', text): e['with_eval_count_str'] += 1
        if 'token' in text.lower(): e['with_token_word'] += 1
    probe['token_coverage_by_arm'] = tok_cover
    # 2) score.json 是否含 token 字段(抽全量键并查)
    sj_keys, sj_tok = set(), 0
    for c in main_cells[:40]:
        p = os.path.join(os.path.dirname(c['transcript']), 'score.json')
        if os.path.exists(p):
            s = open(p, encoding='utf-8', errors='replace').read()
            sj_keys |= set(json.loads(s).keys()) if s.strip().startswith('{') else set()
            if 'token' in s.lower() or 'eval_count' in s: sj_tok += 1
    probe['score_json_keys'] = sorted(sj_keys)
    probe['score_json_with_token_fields'] = sj_tok
    with open(os.path.join(OUT, 'tokens_probe_data.json'), 'w', encoding='utf-8') as f:
        json.dump(probe, f, ensure_ascii=False, indent=1)

    # ---- 控制台摘要 ----
    print('main cells resolved:', len(main_cells), ' ablation cells:', len(abl_cells))
    print('mechanism rows:', len(mech_rows), ' turns rows:', len(tr_rows))
    print('--- arm tool_calls ---')
    for arm, vals in sorted(per_arm_vals.items()):
        print(f'  {arm:10s} n={len(vals):3d} mean={statistics.mean(vals):7.1f} median={statistics.median(vals):6.1f}')
    print('--- mingbird 主臂 finish_gate 总触发 ---')
    fg = sum(v for (a, m, f), v in fam_tot.items() if a == 'Mingbird' and f == 'finish_gate')
    print('  ', fg)
    for variant in ('finish_gate', 'verify_feedback', 'anti_loop', 'flat_prefill'):
        arm = f'ablation:{variant}'
        fams = {f: v for (a, m, f), v in fam_tot.items() if a == arm}
        print(f'--- {arm} ---', fams)
    print('--- per-marker × arm 透视(marker 合计) ---')
    arms_order = ['Mingbird', 'ablation:finish_gate', 'ablation:verify_feedback',
                  'ablation:anti_loop', 'ablation:flat_prefill']
    mm = {}
    for (a, m, k), v in marker_tot.items():
        mm.setdefault((a, k), 0)
        mm[(a, k)] += v
    hdr = ['marker'] + [a.replace('ablation:', 'abl:') for a in arms_order]
    print(' | '.join(hdr))
    for key, zh, fam in MARKERS:
        print(' | '.join([key] + [str(mm.get((a, key), 0)) for a in arms_order]))
    print('quirks:')
    for q in quirks:
        print('  ', q)

if __name__ == '__main__':
    main()
