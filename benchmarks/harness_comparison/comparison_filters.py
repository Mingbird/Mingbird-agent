"""Shared cell filters for the the comparison study analysis chain.

One rule, one implementation. A cell that ended because the inference server
was unreachable is an infrastructure failure, not a harness outcome, and every
consumer of the results directory has to agree on that: the summary, the
failure taxonomy, and the tables all read the same cells independently, and a
rule applied in only one of them produces a report whose numbers disagree with
its own table.

Import from the scripts that need it. They run with ``-I``, so each one puts
its own directory on ``sys.path`` first:

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from comparison_filters import died_on_connection
"""
from __future__ import annotations

from pathlib import Path

CONN_FAIL = (
    "Could not connect to 127.0.0.1:",
    "Cannot connect to API",
    "WinError 10061",      # connection refused: nothing listening
    "WinError 10054",      # connection reset by the peer
    "远程主机强迫关闭",      # reset, localised
)


def died_on_connection(transcript: Path, tail_lines: int = 6) -> bool:
    """Did this cell's run end because the inference server was unreachable?

    On 2026-10-25 the Ollama server died at about 21:49, mid-way through the
    first 9.0B task. Three arms recorded the failure in three different shapes:
    opencode printed ``Cannot connect to API``, goose printed a network error
    and still exited 0 with a zero score, and pi left no score at all. Only the
    last of those looks like an infrastructure failure to the runner. The check
    here reads the cell's own transcript and requires the connection failure to
    be at the *end* of the run, so a transient blip early in a cell that then
    went on to legitimately score zero is not reclassified.
    """
    if not transcript.exists():
        return False
    try:
        txt = transcript.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    lines = [ln for ln in txt.splitlines() if ln.strip()]
    if not lines:
        return False
    tail = "\n".join(lines[-tail_lines:])
    return any(p in tail for p in CONN_FAIL)
