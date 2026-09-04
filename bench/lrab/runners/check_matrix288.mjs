// MyAgents command Detector: 288 final-matrix watcher.
// quiet    -> verdict "running"
// activate -> verdict "complete" (once per completion fingerprint)
//             or "stalled"/"dead" (once per episode fingerprint)
// Reuses matrix288_status.py as the single source of truth. --fixture <file>
// lets trigger-test specs feed precomputed probe JSON without touching live
// state (same contract as check_fpverify.mjs / check_lrab_batch.mjs).
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";

const PY = "D:\\Python312\\python.exe";
const PROBE = "C:\\Users\\99491\\dev\\hummingbird_fp_0902\\bench\\lrab\\runners\\matrix288_status.py";

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
const started = s.cells_started ?? 0;

function quiet(code, msg, next = cp) {
  console.log(JSON.stringify({
    protocolVersion: 1,
    control: { decision: "quiet", reason: { code, message: msg }, nextCheckpoint: { schemaVersion: 1, value: next } },
  }));
}

if (verdict === "running") {
  quiet("batch_running", `288 matrix running: ${started}/288 cells started`,
        { ...cp, lastSeen: verdict, started, lastEpisode: null });
} else if (verdict === "complete") {
  const ok = s.manifest?.ok ?? "?";
  const failed = s.manifest?.failed ?? "?";
  const completeEvent = `matrix288-complete-${ok}-${failed}`;
  if (cp.completeActivated === completeEvent) quiet("already_reported", `Completion already activated (${completeEvent})`);
  else console.log(JSON.stringify({
    protocolVersion: 1,
    control: {
      decision: "activate",
      reason: { code: "matrix288_complete", message: `288 matrix complete: ok=${ok} failed=${failed}` },
      event: { id: completeEvent, kind: "matrix288.batch.complete", occurredAt: new Date().toISOString() },
      nextCheckpoint: { schemaVersion: 1, value: { completeActivated: completeEvent, started } },
    },
    handoff: {
      summary: `288 全公平终局矩阵完赛(ok=${ok}, failed=${failed})`,
      text: `288 格批次已完赛(${started}/288 格启动记录)。请读最新 MATRIX_MANIFEST 历史副本与 RESULTS 汇总,按四大模型段聚合四家 agent 均值,与批次 1/LH 历史基线对比,给出终审结论并报告用户,然后 task exit。`,
      data: s,
    },
  }));
} else { // stalled | dead
  const ageBucket = Math.floor((s.log_age_sec ?? -1) / 1800);
  const episode = `${verdict}:${started}:${ageBucket}`;
  if (cp.lastEpisode === episode) quiet("episode_reported", `Episode ${episode} already activated`);
  else console.log(JSON.stringify({
    protocolVersion: 1,
    control: {
      decision: "activate",
      reason: { code: `matrix288_${verdict}`, message: `288 matrix ${verdict} at ${started}/288 cells` },
      event: { id: `matrix288-${verdict}-${started}`, kind: `matrix288.batch.${verdict}`, occurredAt: new Date().toISOString() },
      nextCheckpoint: { schemaVersion: 1, value: { lastEpisode: episode, started } },
    },
    handoff: {
      summary: `【288 告警】批次${verdict === "dead" ? "进程死亡" : "疑似停滞"}（${started}/288 格启动）`,
      text: `288 批次判定 ${verdict}(${started}/288 格),日志 ${s.log_age_sec ?? "?"} 秒无活动。请诊断驱动/ollama/日志尾部并报告用户;不要自行重启批次,等用户指示。`,
      data: s,
    },
  }));
}
