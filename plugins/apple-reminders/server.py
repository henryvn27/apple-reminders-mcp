#!/usr/bin/env python3
"""Dependency-free MCP server for creating native Apple Reminders."""

import datetime as dt
import json
import subprocess
import sys
from pathlib import Path


PROTOCOL_VERSION = "2025-06-18"
SERVER_VERSION = "0.1.0"
TOOL_NAME = "add_reminder"
BRIDGE = Path(__file__).with_name("reminders.js")
ALLOWED_ARGUMENTS = {"title", "due", "list", "notes", "priority"}
PRIORITIES = {"none": 0, "high": 1, "medium": 5, "low": 9}

TOOL = {
    "name": TOOL_NAME,
    "title": "Add Apple Reminder",
    "description": (
        "Create one reminder in the native Apple Reminders app on this Mac. "
        "Resolve relative dates before calling. Use YYYY-MM-DD for an all-day "
        "reminder or an ISO 8601 date-time with an explicit UTC offset."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "minLength": 1,
                "maxLength": 512,
                "description": "Reminder title.",
            },
            "due": {
                "type": "string",
                "description": (
                    "Optional due value. Use YYYY-MM-DD for all day, or an ISO "
                    "8601 date-time with an explicit offset, such as "
                    "2026-09-01T16:00:00-04:00."
                ),
            },
            "list": {
                "type": "string",
                "minLength": 1,
                "maxLength": 256,
                "description": (
                    "Optional exact Reminders list name. The default list is used "
                    "when omitted. Duplicate list names are rejected."
                ),
            },
            "notes": {
                "type": "string",
                "maxLength": 4096,
                "description": "Optional reminder notes.",
            },
            "priority": {
                "type": "string",
                "enum": ["none", "low", "medium", "high"],
                "default": "none",
            },
        },
        "required": ["title"],
        "additionalProperties": False,
    },
    "annotations": {
        "title": "Add Apple Reminder",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
}


class UserError(Exception):
    pass


def _text(value, field, maximum, required=False):
    if value is None and not required:
        return None
    if not isinstance(value, str):
        raise UserError("%s must be a string" % field)
    value = value.strip()
    if required and not value:
        raise UserError("%s cannot be empty" % field)
    if "\x00" in value:
        raise UserError("%s cannot contain a null byte" % field)
    if len(value) > maximum:
        raise UserError("%s must be at most %d characters" % (field, maximum))
    return value or None


def normalize_arguments(arguments):
    if not isinstance(arguments, dict):
        raise UserError("arguments must be an object")
    unknown = sorted(set(arguments) - ALLOWED_ARGUMENTS)
    if unknown:
        raise UserError("unknown argument%s: %s" % (
            "" if len(unknown) == 1 else "s", ", ".join(unknown)
        ))

    priority = arguments.get("priority", "none")
    if not isinstance(priority, str) or priority not in PRIORITIES:
        raise UserError("priority must be one of: none, low, medium, high")

    due = arguments.get("due")
    due_kind = None
    if due is not None:
        due = _text(due, "due", 64, required=True)
        if len(due) == 10:
            try:
                due = dt.date.fromisoformat(due).isoformat()
            except ValueError:
                raise UserError("due must be a real date in YYYY-MM-DD format")
            due_kind = "all_day"
        else:
            try:
                parsed = dt.datetime.fromisoformat(due.replace("Z", "+00:00"))
            except ValueError:
                raise UserError("due must be an ISO 8601 date-time")
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise UserError("timed due values must include an explicit UTC offset")
            due = parsed.isoformat(timespec="seconds")
            due_kind = "timed"

    return {
        "title": _text(arguments.get("title"), "title", 512, required=True),
        "due": due,
        "due_kind": due_kind,
        "list": _text(arguments.get("list"), "list", 256),
        "notes": _text(arguments.get("notes"), "notes", 4096),
        "priority": PRIORITIES[priority],
        "priority_label": priority,
    }


def invoke_reminders(payload):
    try:
        completed = subprocess.run(
            [
                "/usr/bin/osascript",
                "-l",
                "JavaScript",
                str(BRIDGE),
                json.dumps(payload, ensure_ascii=False),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise UserError("Apple Reminders did not respond within 30 seconds")
    except OSError as error:
        raise UserError("could not launch Apple Reminders automation: %s" % error)

    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        detail = detail.splitlines()[-1] if detail else "unknown automation error"
        raise UserError("Apple Reminders rejected the request: %s" % detail)

    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError:
        raise UserError("Apple Reminders returned an unreadable response")
    if not isinstance(result, dict) or not result.get("id"):
        raise UserError("Apple Reminders did not confirm the created reminder")
    return result


def _tool_result(text, structured=None, is_error=False):
    result = {"content": [{"type": "text", "text": text}]}
    if structured is not None:
        result["structuredContent"] = structured
    if is_error:
        result["isError"] = True
    return result


def call_tool(params):
    if not isinstance(params, dict) or params.get("name") != TOOL_NAME:
        raise UserError("unknown tool")
    try:
        payload = normalize_arguments(params.get("arguments", {}))
        created = invoke_reminders(payload)
    except UserError as error:
        return _tool_result(str(error), is_error=True)

    message = 'Added “%s” to the “%s” Reminders list.' % (
        created["title"], created["list"]
    )
    return _tool_result(message, created)


def _response(message_id, result):
    return {"jsonrpc": "2.0", "id": message_id, "result": result}


def _error(message_id, code, message):
    return {
        "jsonrpc": "2.0",
        "id": message_id,
        "error": {"code": code, "message": message},
    }


def handle_message(message):
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return _error(None, -32600, "Invalid Request")

    method = message.get("method")
    message_id = message.get("id")
    if message_id is None:
        return None

    if method == "initialize":
        return _response(message_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "apple-reminders", "version": SERVER_VERSION},
            "instructions": "Creates reminders only. It cannot read, complete, or delete them.",
        })
    if method == "ping":
        return _response(message_id, {})
    if method == "tools/list":
        return _response(message_id, {"tools": [TOOL]})
    if method == "tools/call":
        try:
            return _response(message_id, call_tool(message.get("params")))
        except UserError as error:
            return _error(message_id, -32602, str(error))
    return _error(message_id, -32601, "Method not found")


def main():
    for raw_line in sys.stdin:
        try:
            message = json.loads(raw_line)
            response = handle_message(message)
        except json.JSONDecodeError:
            response = _error(None, -32700, "Parse error")
        except Exception as error:  # Keep one bad request from killing the MCP process.
            print("apple-reminders server error: %s" % error, file=sys.stderr)
            response = _error(None, -32603, "Internal error")
        if response is not None:
            print(json.dumps(response, ensure_ascii=False, separators=(",", ":")), flush=True)


if __name__ == "__main__":
    main()
