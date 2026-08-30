import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock


PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN))
import server  # noqa: E402


class ServerTests(unittest.TestCase):
    def test_protocol_round_trip_lists_one_write_tool(self):
        requests = "\n".join([
            json.dumps({
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-06-18"},
            }),
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
            "",
        ])
        completed = subprocess.run(
            ["/usr/bin/python3", str(PLUGIN / "server.py")],
            input=requests,
            capture_output=True,
            text=True,
            check=True,
        )
        responses = [json.loads(line) for line in completed.stdout.splitlines()]
        self.assertEqual(responses[0]["result"]["protocolVersion"], "2025-06-18")
        self.assertEqual(responses[1]["result"]["tools"][0]["name"], "add_reminder")
        self.assertFalse(responses[1]["result"]["tools"][0]["annotations"]["readOnlyHint"])

    def test_call_normalizes_dates_and_priority(self):
        created = {
            "id": "test-id",
            "title": "Submit form",
            "list": "School",
            "due": "2026-09-01T16:00:00-04:00",
            "priority": "high",
        }
        with mock.patch.object(server, "invoke_reminders", return_value=created) as invoke:
            result = server.call_tool({
                "name": "add_reminder",
                "arguments": {
                    "title": " Submit form ",
                    "due": "2026-09-01T16:00:00-04:00",
                    "list": " School ",
                    "priority": "high",
                },
            })
        payload = invoke.call_args.args[0]
        self.assertEqual(payload["title"], "Submit form")
        self.assertEqual(payload["list"], "School")
        self.assertEqual(payload["priority"], 1)
        self.assertEqual(payload["due_kind"], "timed")
        self.assertEqual(result["structuredContent"]["id"], "test-id")

    def test_all_day_and_invalid_inputs(self):
        normalized = server.normalize_arguments({"title": "Pack", "due": "2026-09-02"})
        self.assertEqual(normalized["due_kind"], "all_day")
        with self.assertRaisesRegex(server.UserError, "explicit UTC offset"):
            server.normalize_arguments({"title": "Pack", "due": "2026-09-02T09:00:00"})
        with self.assertRaisesRegex(server.UserError, "unknown argument"):
            server.normalize_arguments({"title": "Pack", "delete": True})
        with self.assertRaisesRegex(server.UserError, "priority must be"):
            server.normalize_arguments({"title": "Pack", "priority": ["high"]})


if __name__ == "__main__":
    unittest.main()
