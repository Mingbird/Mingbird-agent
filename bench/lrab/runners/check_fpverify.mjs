// MyAgents command Detector: fp-0902 verification batch watcher.
// quiet    -> verdict "running"
// activate -> verdict "complete" (once per completion fingerprint)
//             or "stalled"/"dead" (once per episode fingerprint)
// Reuses fpverify_status.py as the single source of truth. --fixture <file>
// lets trigger-test specs feed precomputed probe JSON without touching live
// state (mirrors check_lrab_batch.mjs, batch-1 lessons baked in: episode
// fingerprints, completion keyed on state not a deterministic id).
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";

const PY = "D:\\Python312\\python.exe";
const PROBE = "C:\\Users\\99491\\dev\\hummingbird\\bench\\lrab\\runners\\fpverify_status.py";

function readStdin() {
  try {
    return JSON.parse(readFileSync(0, "utf8"));
  } catch {
    return { checkpoint: { revision: 0, value: null } };
  }
}

function probe() {
  const fsIdx = process.argv.indexOf("--fixture");
  if (fsIdx > 0) return JSON.parse(readFileSync(process.argv[fsIdx + 1], "utf8"));
  const r = spawnSync(PY, [PROBE], { encoding: "utf8", timeout: 50000 });
  if (r.error || r.status !== 0) {
    console.error("probe failed:", r.error || r.stderr);
    process.exit(3); // harness failure, not a business decision
  }
  return JSON.parse(r.stdout);
}

const invocation = readStdin();
const cp = invocation.checkpoint?.value ?? {};
const s = probe();
const verdict = s.verdict;
const done = s.cells_done ?? 0;

function quiet(code, msg, next = cp) {
  console.log(JSON.stringify({
    protocolVersion: 1,
    control: { decision: "quiet", reason: { code, message: msg }, nextCheckpoint: { schemaVersion: 1, value: next } },
  }));
}

if (verdict === "running") {
  quiet("batch_running", `fpverify running: ${done}/3 cells scored`,
        { ...cp, lastSeen: verdict, cellsDone: done, lastEpisode: null });
} else if (verdict === "complete") {
  const newestLeaf = String(s.newest_artifact ?? "?").split(/[\\/]/).slice(-2, -1)[0] || "?";
  const completeEvent = `fpverify-complete-${done}-${newestLeaf}`;
  if (cp.completeActivated === completeEvent) quiet("already_reported", `Completion already activated (${completeEvent})`);
  else {
    const totals = (s.cells ?? []).map(c => `${c.key}=${c.total ?? c.failure_mode ?? "?"}`).join(", ");
    console.log(JSON.stringify({
      protocolVersion: 1,
      control: {
        decision: "activate",
        reason: { code: "fpverify_complete", message: `fpverify complete: ${done}/3 cells` },
        event: { id: completeEvent, kind: "fpverify.batch.complete", occurredAt: new Date().toISOString() },
        nextCheckpoint: { schemaVersion: 1, value: { completeActivated: completeEvent, cellsDone: done } },
      },
      handoff: {
        summary: `fp-0902 验证批完成（${done}/3 格）`,
        text: `3 个死格验收重跑已完成。各格结果: ${totals}。请汇总对比批次 1 同格基线,报告用户验收结论。`,
        data: s,
      },
    }));
  }
} else { // stalled | dead
  const leaf = String(s.newest_artifact ?? "?").split(/[\\/]/).pop();
  const ageBucket = Math.floor((s.newest_age_sec ?? -1) / 1800);
  const episode = `${verdict}:${done}:${leaf}:${ageBucket}`;
  if (cp.lastEpisode === episode) quiet("episode_reported", `Episode ${episode} already activated`);
  else console.log(JSON.stringify({
    protocolVersion: 1,
    control: {
      decision: "activate",
      reason: { code: `fpverify_${verdict}`, message: `fpverify ${verdict} at ${done}/3 cells` },
      event: { id: `fpverify-${verdict}-${done}-${leaf}`, kind: `fpverify.batch.${verdict}`, occurredAt: new Date().toISOString() },
      nextCheckpoint: { schemaVersion: 1, value: { lastEpisode: episode, cellsDone: done } },
    },
    handoff: {
      summary: `【验证批告警】fp-0902 批次${verdict === "dead" ? "进程死亡" : "疑似停滞"}（${done}/3 格完成）`,
      text: `验证批判定 ${verdict}（${done}/3 格），最后活动 ${s.newest_age_sec ?? "?"} 秒前。请检查驱动与 ollama 状态并报告用户,不要自行重启批次。`,
      data: s,
    },
  }));
}
