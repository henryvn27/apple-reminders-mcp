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
    def test_protocol_round_trip_lists_safe_lifecycle_tools(self):
        requests = "\n".join(
            [
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {"protocolVersion": "2025-06-18"},
                    }
                ),
                json.dumps(
                    {"jsonrpc": "2.0", "method": "notifications/initialized"}
                ),
                json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
                "",
            ]
        )
        completed = subprocess.run(
            ["/usr/bin/python3", str(PLUGIN / "server.py")],
            input=requests,
            capture_output=True,
            text=True,
            check=True,
        )
        responses = [json.loads(line) for line in completed.stdout.splitlines()]
        self.assertEqual(responses[0]["result"]["protocolVersion"], "2025-06-18")
        self.assertEqual(responses[0]["result"]["serverInfo"]["version"], "0.2.0")
        tools = responses[1]["result"]["tools"]
        self.assertEqual(
            [tool["name"] for tool in tools],
            [
                "list_reminder_lists",
                "search_reminders",
                "get_reminder",
                "add_reminder",
                "update_reminder",
                "set_reminder_completed",
                "delete_reminder",
            ],
        )

    def test_annotations_match_tool_effects(self):
        tools = {tool["name"]: tool["annotations"] for tool in server.TOOLS}
        for name in ("list_reminder_lists", "search_reminders", "get_reminder"):
            self.assertTrue(tools[name]["readOnlyHint"])
            self.assertFalse(tools[name]["destructiveHint"])
            self.assertTrue(tools[name]["idempotentHint"])
        self.assertFalse(tools["add_reminder"]["readOnlyHint"])
        self.assertFalse(tools["add_reminder"]["idempotentHint"])
        self.assertTrue(tools["delete_reminder"]["destructiveHint"])
        self.assertFalse(tools["delete_reminder"]["idempotentHint"])

    def test_add_normalizes_dates_and_priority(self):
        payload = server.normalize_arguments(
            "add_reminder",
            {
                "title": " Submit form ",
                "due": "2026-09-01T16:00:00-04:00",
                "list": " School ",
                "priority": "high",
            },
        )
        self.assertEqual(payload["action"], "add_reminder")
        self.assertEqual(payload["title"], "Submit form")
        self.assertEqual(payload["list"], "School")
        self.assertEqual(payload["priority"], 1)
        self.assertEqual(payload["priority_label"], "high")
        self.assertEqual(payload["due_kind"], "timed")

        all_day = server.normalize_arguments(
            "add_reminder", {"title": "Pack", "due": "2026-09-02"}
        )
        self.assertEqual(all_day["due_kind"], "all_day")

    def test_search_normalizes_filters_and_limit(self):
        payload = server.normalize_arguments(
            "search_reminders",
            {
                "query": " goggles ",
                "list": " School ",
                "completed": "all",
                "limit": 25,
            },
        )
        self.assertEqual(
            payload,
            {
                "action": "search_reminders",
                "query": "goggles",
                "list": "School",
                "completed": "all",
                "limit": 25,
            },
        )
        defaults = server.normalize_arguments("search_reminders", {})
        self.assertEqual(defaults["completed"], "open")
        self.assertEqual(defaults["limit"], 50)

    def test_update_is_sparse_and_can_clear_notes(self):
        payload = server.normalize_arguments(
            "update_reminder",
            {
                "id": " reminder-id ",
                "notes": "  ",
                "priority": "none",
                "list": "Personal",
            },
        )
        self.assertEqual(
            payload,
            {
                "action": "update_reminder",
                "id": "reminder-id",
                "notes": "",
                "priority": 0,
                "priority_label": "none",
                "list": "Personal",
            },
        )
        with self.assertRaisesRegex(server.UserError, "at least one field"):
            server.normalize_arguments("update_reminder", {"id": "reminder-id"})

    def test_exact_id_mutations_validate_types(self):
        completed = server.normalize_arguments(
            "set_reminder_completed", {"id": "id-1", "completed": False}
        )
        self.assertEqual(
            completed,
            {
                "action": "set_reminder_completed",
                "id": "id-1",
                "completed": False,
            },
        )
        deleted = server.normalize_arguments("delete_reminder", {"id": "id-1"})
        self.assertEqual(deleted, {"action": "delete_reminder", "id": "id-1"})
        with self.assertRaisesRegex(server.UserError, "completed must be a boolean"):
            server.normalize_arguments(
                "set_reminder_completed", {"id": "id-1", "completed": "yes"}
            )

    def test_invalid_inputs_fail_closed(self):
        cases = [
            (
                "add_reminder",
                {"title": "Pack", "due": "2026-09-02T09:00:00"},
                "explicit UTC offset",
            ),
            ("search_reminders", {"limit": True}, "integer from 1 to 200"),
            ("search_reminders", {"completed": "maybe"}, "completed must be"),
            ("get_reminder", {"id": ""}, "id cannot be empty"),
            ("list_reminder_lists", {"query": "x"}, "unknown argument"),
            ("add_reminder", {"title": "Pack", "delete": True}, "unknown argument"),
        ]
        for name, arguments, message in cases:
            with self.subTest(name=name, arguments=arguments):
                with self.assertRaisesRegex(server.UserError, message):
                    server.normalize_arguments(name, arguments)

    def test_call_tool_dispatches_action_and_returns_structured_content(self):
        result_by_name = {
            "list_reminder_lists": {"lists": [{"name": "Reminders"}]},
            "search_reminders": {"reminders": [{"title": "Pack"}]},
            "get_reminder": {
                "reminder": {
                    "title": "Pack",
                    "list": "Reminders",
                    "completed": False,
                }
            },
            "add_reminder": {
                "reminder": {"title": "Pack", "list": "Reminders"}
            },
            "update_reminder": {"reminder": {"title": "Pack shoes"}},
            "set_reminder_completed": {
                "reminder": {"title": "Pack", "completed": True}
            },
            "delete_reminder": {"deleted": {"title": "Pack"}},
        }
        arguments = {
            "list_reminder_lists": {},
            "search_reminders": {},
            "get_reminder": {"id": "id-1"},
            "add_reminder": {"title": "Pack"},
            "update_reminder": {"id": "id-1", "title": "Pack shoes"},
            "set_reminder_completed": {"id": "id-1", "completed": True},
            "delete_reminder": {"id": "id-1"},
        }
        for name, native_result in result_by_name.items():
            with self.subTest(name=name):
                with mock.patch.object(
                    server, "invoke_reminders", return_value=native_result
                ) as invoke:
                    result = server.call_tool(
                        {"name": name, "arguments": arguments[name]}
                    )
                self.assertEqual(result["structuredContent"], native_result)
                self.assertEqual(invoke.call_args.args[0]["action"], name)
                self.assertNotIn("isError", result)

    def test_native_errors_become_tool_errors(self):
        with mock.patch.object(
            server,
            "invoke_reminders",
            side_effect=server.UserError("native failure"),
        ):
            result = server.call_tool(
                {"name": "get_reminder", "arguments": {"id": "id-1"}}
            )
        self.assertTrue(result["isError"])
        self.assertEqual(result["content"][0]["text"], "native failure")


if __name__ == "__main__":
    unittest.main()
