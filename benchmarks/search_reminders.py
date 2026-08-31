#!/usr/bin/env python3
"""Native Apple Reminders search benchmark with exact fixture cleanup."""

import argparse
import hashlib
import json
import math
import platform
import statistics
import subprocess
import tempfile
import time
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BRIDGE = ROOT / "plugins" / "apple-reminders" / "reminders.js"
QUERY = "speedproofneedle"
FIXTURE_COUNT = 24
WARMUPS = 2
RUNS = 7


def invoke(bridge, payload, *, timeout=180):
    completed = subprocess.run(
        [
            "/usr/bin/osascript",
            "-l",
            "JavaScript",
            str(bridge),
            json.dumps(payload, ensure_ascii=False),
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(detail.splitlines()[-1] if detail else "automation failed")
    result = json.loads(completed.stdout)
    if not isinstance(result, dict):
        raise RuntimeError("automation returned a non-object result")
    return result


def run_jxa(source, *arguments, timeout=300):
    script_path = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as script:
            script.write(source)
            script_path = Path(script.name)
        completed = subprocess.run(
            [
                "/usr/bin/osascript",
                "-l",
                "JavaScript",
                str(script_path),
                *arguments,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    finally:
        if script_path is not None:
            script_path.unlink(missing_ok=True)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(detail.splitlines()[-1] if detail else "automation failed")
    result = json.loads(completed.stdout)
    if not isinstance(result, dict):
        raise RuntimeError("automation returned a non-object result")
    return result


def create_fixture(list_name):
    source = """
function run(argv) {
  const input = JSON.parse(argv[0]);
  const reminders = Application("Reminders");
  const list = reminders.List({ name: input.name });
  reminders.defaultAccount().lists.push(list);
  const ids = [];
  for (let index = 0; index < input.count; index += 1) {
    const reminder = reminders.Reminder({
      name: index === 0 ? "SpeedProofNeedle title 00" : `Fixture ${String(index).padStart(2, "0")}`,
      body: "benchmark fixture",
      priority: 0,
      flagged: false,
    });
    list.reminders.push(reminder);
    ids.push(reminder.id());
  }
  return JSON.stringify({ list_id: list.id(), reminder_ids: ids });
}
"""
    return run_jxa(
        source,
        json.dumps({"name": list_name, "count": FIXTURE_COUNT}),
        timeout=300,
    )


def delete_fixture_list(list_id):
    source = """
function run(argv) {
  const id = argv[0];
  const reminders = Application("Reminders");
  const list = reminders.lists().find((candidate) => candidate.id() === id);
  if (!list) return JSON.stringify({ deleted: false, missing: true });
  reminders.delete(list);
  const remains = reminders.lists().some((candidate) => candidate.id() === id);
  if (remains) throw new Error("fixture list still exists after deletion");
  return JSON.stringify({ deleted: true, missing: false });
}
"""
    return run_jxa(source, list_id, timeout=180)


def verify_lifecycle(bridge, list_id):
    created = invoke(
        bridge,
        {
            "action": "add_reminder",
            "title": "Lifecycle original",
            "list_id": list_id,
            "notes": "temporary",
            "priority": 0,
            "flagged": False,
            "due": None,
            "due_kind": None,
        },
    )["reminder"]
    reminder_id = created["id"]
    updated = invoke(
        bridge,
        {
            "action": "update_reminder",
            "id": reminder_id,
            "title": "Lifecycle updated",
            "notes": "updated",
            "priority": 1,
            "flagged": True,
        },
    )["reminder"]
    if (
        updated["title"] != "Lifecycle updated"
        or updated["notes"] != "updated"
        or updated["priority"] != "high"
        or not updated["flagged"]
    ):
        raise RuntimeError("update lifecycle verification failed")
    completed = invoke(
        bridge,
        {"action": "set_reminder_completed", "id": reminder_id, "completed": True},
    )["reminder"]
    if not completed["completed"]:
        raise RuntimeError("complete lifecycle verification failed")
    reopened = invoke(
        bridge,
        {"action": "set_reminder_completed", "id": reminder_id, "completed": False},
    )["reminder"]
    if reopened["completed"]:
        raise RuntimeError("reopen lifecycle verification failed")
    deleted = invoke(
        bridge, {"action": "delete_reminder", "id": reminder_id}
    )["deleted"]
    if deleted["id"] != reminder_id:
        raise RuntimeError("delete lifecycle verification failed")
    try:
        invoke(bridge, {"action": "get_reminder", "id": reminder_id})
    except RuntimeError:
        return {
            "add": "passed",
            "update": "passed",
            "complete": "passed",
            "reopen": "passed",
            "delete": "passed",
        }
    raise RuntimeError("deleted lifecycle reminder is still readable")


def percentile(values, proportion):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * proportion) - 1)]


def benchmark(bridge, phase, timeout):
    list_id = None
    result = None
    cleanup = None
    try:
        list_name = "Apple Reminders MCP Speedup Proof %s" % uuid.uuid4().hex[:12]
        fixture = create_fixture(list_name)
        list_id = fixture["list_id"]
        fixture_ids = fixture["reminder_ids"]
        expected_ids = fixture_ids[:1]
        if len(set(fixture_ids)) != FIXTURE_COUNT:
            raise RuntimeError("fixture reminder IDs are not unique")
        expected_digest = hashlib.sha256(
            "\n".join(expected_ids).encode()
        ).hexdigest()

        payload = {
            "action": "search_reminders",
            "query": QUERY,
            "list_id": list_id,
            "completed": "all",
            "offset": 0,
            "limit": 200,
        }
        completed_warmups = 0
        timed_out = False
        for _ in range(WARMUPS):
            try:
                warmup = invoke(bridge, payload, timeout=timeout)
            except subprocess.TimeoutExpired:
                if phase != "before":
                    raise
                timed_out = True
                break
            ids = [item["id"] for item in warmup["reminders"]]
            digest = hashlib.sha256("\n".join(ids).encode()).hexdigest()
            if digest != expected_digest:
                raise RuntimeError("warmup result differs from the fixture oracle")
            completed_warmups += 1

        timings = []
        count = None
        if not timed_out:
            for _ in range(RUNS):
                started = time.perf_counter()
                measured = invoke(bridge, payload, timeout=timeout)
                timings.append(time.perf_counter() - started)
                ids = [item["id"] for item in measured["reminders"]]
                digest = hashlib.sha256("\n".join(ids).encode()).hexdigest()
                if digest != expected_digest:
                    raise RuntimeError(
                        "measured result differs from the fixture oracle"
                    )
                count = measured["count"]
            if count != 1:
                raise RuntimeError("expected 1 query match, got %r" % count)
        lifecycle = verify_lifecycle(bridge, list_id)
        result = {
            "schema_version": 1,
            "phase": phase,
            "bridge_sha256": hashlib.sha256(bridge.read_bytes()).hexdigest(),
            "system": {
                "platform": platform.platform(),
                "python": platform.python_version(),
            },
            "fixture": {
                "reminders": FIXTURE_COUNT,
                "expected_matches": 1,
                "query": QUERY,
            },
            "status": "timed_out" if timed_out else "completed",
            "protocol": {
                "planned_warmups": WARMUPS,
                "completed_warmups": completed_warmups,
                "planned_runs": RUNS,
                "completed_runs": len(timings),
                "timeout_seconds": timeout,
            },
            "timings_seconds": [round(value, 6) for value in timings],
            "median_seconds": (
                round(statistics.median(timings), 6) if timings else None
            ),
            "p95_seconds": (
                round(percentile(timings, 0.95), 6) if timings else None
            ),
            "timeout_lower_bound_seconds": timeout if timed_out else None,
            "ordered_id_digest": expected_digest,
            "result_count": count,
            "lifecycle": lifecycle,
        }
    finally:
        if list_id is not None:
            cleanup = delete_fixture_list(list_id)
    if result is None:
        raise RuntimeError("benchmark did not produce a result")
    if not cleanup.get("deleted"):
        raise RuntimeError("fixture list cleanup was not confirmed")
    result["fixture_cleanup"] = "passed"
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("before", "after"), required=True)
    parser.add_argument("--bridge", type=Path, default=DEFAULT_BRIDGE)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    if args.timeout < 1:
        parser.error("--timeout must be positive")
    result = benchmark(args.bridge.resolve(), args.phase, args.timeout)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
