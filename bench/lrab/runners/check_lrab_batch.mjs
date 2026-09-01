// MyAgents command Detector: LRAB active-batch watcher (target batch is
// selected by batch_watch.json next to batch_status.py).
// quiet  -> verdict "running" (or an episode already activated)
// activate -> verdict "complete" (once) or "stalled"/"idle" (once per episode)
//
// Reuses batch_status.py as the single source of truth. --fixture <file> lets
// trigger-test specs feed precomputed probe JSON without touching live state.
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";

const PY = "D:\\Python312\\python.exe";
const PROBE = "C:\\Users\\99491\\dev\\hummingbird\\bench\\lrab\\runners\\batch_status.py";

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
const target = s.target ?? 64;

function quiet(code, msg, next = cp) {
  console.log(JSON.stringify({
    protocolVersion: 1,
    control: { decision: "quiet", reason: { code, message: msg }, nextCheckpoint: { schemaVersion: 1, value: next } },
  }));
}

if (verdict === "running") {
  // Chain recovered since the last alert -> close the episode so a FUTURE
  // stall re-fires. 2026-09-01 lesson: keeping lastEpisode across a recovery
  // muted every tick when the chain died again with the same cells_done.
  quiet("batch_running", `Batch running: ${done}/${target} cells done`,
        { ...cp, lastSeen: verdict, cellsDone: done, lastEpisode: null });
} else if (verdict === "paused") {
  quiet("batch_paused", `Batch paused by operator: ${done}/${target} cells done`, cp);
} else if (verdict === "complete") {
  if (cp.completeActivated) quiet("already_reported", "Batch completion already activated once");
  else console.log(JSON.stringify({
    protocolVersion: 1,
    control: {
      decision: "activate",
      reason: { code: "batch_complete", message: `LRAB batch complete: ${done}/${target} cells` },
      event: { id: `lrab-batch-complete-${done}`, kind: "lrab.batch.complete", occurredAt: new Date().toISOString() },
      nextCheckpoint: { schemaVersion: 1, value: { completeActivated: true, cellsDone: done } },
    },
    handoff: {
      summary: `LRAB 批次已完成（${done}/${target}）`,
      text: `批次判定 complete（${done}/${target} 格有 score.json）。请按 triggers/task-action.md 汇总成绩并报告用户。`,
      data: s,
    },
  }));
} else { // stalled | idle
  // Episode identity = verdict + progress + newest artifact + age bucket.
  // cells_done alone is not enough: a tree death leaves cells_done frozen
  // (husk dirs carry no score.json), so a SECOND death looked identical to
  // the first alert and was suppressed forever.
  const leaf = String(s.newest_artifact ?? "?").split(/[\\/]/).pop();
  const ageBucket = Math.floor((s.newest_age_sec ?? -1) / 1800);
  const episode = `${verdict}:${done}:${leaf}:${ageBucket}`;
  if (cp.lastEpisode === episode) quiet("episode_reported", `Episode ${episode} already activated`);
  else console.log(JSON.stringify({
    protocolVersion: 1,
    control: {
      decision: "activate",
      reason: { code: `batch_${verdict}`, message: `LRAB batch ${verdict} at ${done}/${target} cells` },
      event: { id: `lrab-batch-${verdict}-${done}`, kind: `lrab.batch.${verdict}`, occurredAt: new Date().toISOString() },
      nextCheckpoint: { schemaVersion: 1, value: { lastEpisode: episode, cellsDone: done } },
    },
    handoff: {
      summary: `【批次告警】LRAB 批次疑似${verdict === "idle" ? "无产出" : "停滞"}（${done}/${target}）`,
      text: `批次判定 ${verdict}（${done}/${target} 格），最后活动 ${s.newest_age_sec ?? "?"} 秒前。请检查原因并报告用户，不要自行重启批次。`,
      data: s,
    },
  }));
}
