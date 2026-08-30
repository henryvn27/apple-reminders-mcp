#!/usr/bin/env python3
"""Dependency-free MCP server for native Apple Reminders."""

import datetime as dt
import json
import subprocess
import sys
from pathlib import Path


PROTOCOL_VERSION = "2025-06-18"
SERVER_VERSION = "0.3.0"
BRIDGE = Path(__file__).with_name("reminders.js")
PRIORITIES = {"none": 0, "high": 1, "medium": 5, "low": 9}


def _annotations(title, *, read_only, destructive=False, idempotent=True):
    return {
        "title": title,
        "readOnlyHint": read_only,
        "destructiveHint": destructive,
        "idempotentHint": idempotent,
        "openWorldHint": False,
    }


DUE_SCHEMA = {
    "type": "string",
    "description": (
        "Use YYYY-MM-DD for an all-day due date, or an ISO 8601 date-time "
        "with an explicit UTC offset, such as 2026-09-01T16:00:00-04:00."
    ),
}
LOCAL_DATE_SCHEMA = {
    "type": "string",
    "pattern": r"^\d{4}-\d{2}-\d{2}$",
    "description": "Local calendar date in YYYY-MM-DD format, inclusive.",
}
ID_SCHEMA = {
    "type": "string",
    "minLength": 1,
    "maxLength": 1024,
    "description": "Exact native reminder ID returned by a read tool.",
}
LIST_SCHEMA = {
    "type": "string",
    "minLength": 1,
    "maxLength": 256,
    "description": "Exact Reminders list name. Duplicate names are rejected.",
}
LIST_ID_SCHEMA = {
    "type": "string",
    "minLength": 1,
    "maxLength": 1024,
    "description": "Exact native list ID returned by list_reminder_lists.",
}
PRIORITY_SCHEMA = {
    "type": "string",
    "enum": ["none", "low", "medium", "high"],
}

TOOLS = [
    {
        "name": "list_reminder_lists",
        "title": "List Apple Reminder Lists",
        "description": "List native Reminders lists with their IDs and reminder counts.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        "annotations": _annotations("List Apple Reminder Lists", read_only=True),
    },
    {
        "name": "create_reminder_list",
        "title": "Create Apple Reminder List",
        "description": "Create one list in the default Reminders account.",
        "inputSchema": {
            "type": "object",
            "properties": {"name": LIST_SCHEMA},
            "required": ["name"],
            "additionalProperties": False,
        },
        "annotations": _annotations(
            "Create Apple Reminder List", read_only=False, idempotent=False
        ),
    },
    {
        "name": "rename_reminder_list",
        "title": "Rename Apple Reminder List",
        "description": "Rename one list by its exact native list ID.",
        "inputSchema": {
            "type": "object",
            "properties": {"id": LIST_ID_SCHEMA, "name": LIST_SCHEMA},
            "required": ["id", "name"],
            "additionalProperties": False,
        },
        "annotations": _annotations("Rename Apple Reminder List", read_only=False),
    },
    {
        "name": "search_reminders",
        "title": "Search Apple Reminders",
        "description": (
            "Read existing reminders. Optionally search titles and notes, limit "
            "the search to an exact list, filter by local due-date range or flag, "
            "and page through open, completed, or all items."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "maxLength": 512,
                    "description": "Optional case-insensitive text in the title or notes.",
                },
                "list": LIST_SCHEMA,
                "list_id": LIST_ID_SCHEMA,
                "completed": {
                    "type": "string",
                    "enum": ["open", "completed", "all"],
                    "default": "open",
                },
                "flagged": {"type": "boolean"},
                "due_start": LOCAL_DATE_SCHEMA,
                "due_end": LOCAL_DATE_SCHEMA,
                "offset": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 10000,
                    "default": 0,
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 200,
                    "default": 50,
                },
            },
            "additionalProperties": False,
        },
        "annotations": _annotations("Search Apple Reminders", read_only=True),
    },
    {
        "name": "get_reminder",
        "title": "Get Apple Reminder",
        "description": "Read one native reminder by its exact ID.",
        "inputSchema": {
            "type": "object",
            "properties": {"id": ID_SCHEMA},
            "required": ["id"],
            "additionalProperties": False,
        },
        "annotations": _annotations("Get Apple Reminder", read_only=True),
    },
    {
        "name": "add_reminder",
        "title": "Add Apple Reminder",
        "description": (
            "Create one reminder in the native Apple Reminders app. Resolve "
            "relative dates before calling."
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
                "due": DUE_SCHEMA,
                "list": LIST_SCHEMA,
                "list_id": LIST_ID_SCHEMA,
                "notes": {
                    "type": "string",
                    "maxLength": 4096,
                    "description": "Optional reminder notes.",
                },
                "priority": {**PRIORITY_SCHEMA, "default": "none"},
                "flagged": {"type": "boolean", "default": False},
            },
            "required": ["title"],
            "additionalProperties": False,
        },
        "annotations": _annotations(
            "Add Apple Reminder", read_only=False, idempotent=False
        ),
    },
    {
        "name": "update_reminder",
        "title": "Update Apple Reminder",
        "description": (
            "Update one reminder by exact ID. Supports title, notes, priority, "
            "due value, flag, and moving it to an existing list. Empty notes clear them. "
            "Switching an existing due value between all-day and timed is rejected "
            "because Apple automation cannot do it without leaving stale date state."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": ID_SCHEMA,
                "title": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 512,
                },
                "due": DUE_SCHEMA,
                "list": LIST_SCHEMA,
                "list_id": LIST_ID_SCHEMA,
                "notes": {"type": "string", "maxLength": 4096},
                "priority": PRIORITY_SCHEMA,
                "flagged": {"type": "boolean"},
            },
            "required": ["id"],
            "additionalProperties": False,
        },
        "annotations": _annotations("Update Apple Reminder", read_only=False),
    },
    {
        "name": "set_reminder_completed",
        "title": "Complete or Reopen Apple Reminder",
        "description": "Complete or reopen one reminder by its exact ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": ID_SCHEMA,
                "completed": {"type": "boolean"},
            },
            "required": ["id", "completed"],
            "additionalProperties": False,
        },
        "annotations": _annotations(
            "Complete or Reopen Apple Reminder", read_only=False
        ),
    },
    {
        "name": "delete_reminder",
        "title": "Delete Apple Reminder",
        "description": "Permanently delete one reminder by its exact ID.",
        "inputSchema": {
            "type": "object",
            "properties": {"id": ID_SCHEMA},
            "required": ["id"],
            "additionalProperties": False,
        },
        "annotations": _annotations(
            "Delete Apple Reminder",
            read_only=False,
            destructive=True,
            idempotent=False,
        ),
    },
]
TOOL_NAMES = {tool["name"] for tool in TOOLS}


class UserError(Exception):
    pass


def _arguments(arguments, allowed):
    if not isinstance(arguments, dict):
        raise UserError("arguments must be an object")
    unknown = sorted(set(arguments) - allowed)
    if unknown:
        raise UserError(
            "unknown argument%s: %s"
            % ("" if len(unknown) == 1 else "s", ", ".join(unknown))
        )
    return arguments


def _text(value, field, maximum, *, required=False, allow_empty=False):
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
    return value if value or allow_empty else None


def _due(value):
    value = _text(value, "due", 64, required=True)
    if len(value) == 10:
        try:
            return dt.date.fromisoformat(value).isoformat(), "all_day"
        except ValueError:
            raise UserError("due must be a real date in YYYY-MM-DD format")
    return _timed_date_time(value, "due"), "timed"


def _timed_date_time(value, field):
    value = _text(value, field, 64, required=True)
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise UserError("%s must be an ISO 8601 date-time" % field)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise UserError("%s must include an explicit UTC offset" % field)
    return parsed.isoformat(timespec="seconds")


def _local_date(value, field):
    value = _text(value, field, 10, required=True)
    try:
        return dt.date.fromisoformat(value).isoformat()
    except ValueError:
        raise UserError("%s must be a real date in YYYY-MM-DD format" % field)


def _priority(value, default=None):
    if value is None and default is not None:
        value = default
    if not isinstance(value, str) or value not in PRIORITIES:
        raise UserError("priority must be one of: none, low, medium, high")
    return PRIORITIES[value], value


def _id(arguments):
    return _text(arguments.get("id"), "id", 1024, required=True)


def _list_target(arguments, payload):
    if "list" in arguments and "list_id" in arguments:
        raise UserError("use either list or list_id, not both")
    if "list" in arguments:
        payload["list"] = _text(arguments["list"], "list", 256, required=True)
    if "list_id" in arguments:
        payload["list_id"] = _text(
            arguments["list_id"], "list_id", 1024, required=True
        )


def _boolean(arguments, field, payload, *, default=None):
    if field not in arguments:
        if default is not None:
            payload[field] = default
        return
    value = arguments[field]
    if not isinstance(value, bool):
        raise UserError("%s must be a boolean" % field)
    payload[field] = value


def normalize_arguments(name, arguments):
    if name == "list_reminder_lists":
        _arguments(arguments, set())
        return {"action": name}

    if name == "create_reminder_list":
        arguments = _arguments(arguments, {"name"})
        return {
            "action": name,
            "name": _text(arguments.get("name"), "name", 256, required=True),
        }

    if name == "rename_reminder_list":
        arguments = _arguments(arguments, {"id", "name"})
        return {
            "action": name,
            "id": _id(arguments),
            "name": _text(arguments.get("name"), "name", 256, required=True),
        }

    if name == "search_reminders":
        arguments = _arguments(
            arguments,
            {
                "query",
                "list",
                "list_id",
                "completed",
                "flagged",
                "due_start",
                "due_end",
                "offset",
                "limit",
            },
        )
        completed = arguments.get("completed", "open")
        if completed not in {"open", "completed", "all"}:
            raise UserError("completed must be one of: open, completed, all")
        limit = arguments.get("limit", 50)
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
            raise UserError("limit must be an integer from 1 to 200")
        offset = arguments.get("offset", 0)
        if (
            isinstance(offset, bool)
            or not isinstance(offset, int)
            or not 0 <= offset <= 10000
        ):
            raise UserError("offset must be an integer from 0 to 10000")
        payload = {
            "action": name,
            "query": _text(arguments.get("query"), "query", 512),
            "completed": completed,
            "offset": offset,
            "limit": limit,
        }
        _list_target(arguments, payload)
        _boolean(arguments, "flagged", payload)
        if "due_start" in arguments:
            payload["due_start"] = _local_date(arguments["due_start"], "due_start")
        if "due_end" in arguments:
            payload["due_end"] = _local_date(arguments["due_end"], "due_end")
        if payload.get("due_start") and payload.get("due_end"):
            if payload["due_start"] > payload["due_end"]:
                raise UserError("due_start must be on or before due_end")
        return payload

    if name in {"get_reminder", "delete_reminder"}:
        arguments = _arguments(arguments, {"id"})
        return {"action": name, "id": _id(arguments)}

    if name == "add_reminder":
        arguments = _arguments(
            arguments,
            {
                "title",
                "due",
                "list",
                "list_id",
                "notes",
                "priority",
                "flagged",
            },
        )
        priority, priority_label = _priority(arguments.get("priority"), "none")
        due = due_kind = None
        if "due" in arguments:
            due, due_kind = _due(arguments["due"])
        payload = {
            "action": name,
            "title": _text(arguments.get("title"), "title", 512, required=True),
            "due": due,
            "due_kind": due_kind,
            "notes": _text(arguments.get("notes"), "notes", 4096),
            "priority": priority,
            "priority_label": priority_label,
        }
        _list_target(arguments, payload)
        _boolean(arguments, "flagged", payload, default=False)
        return payload

    if name == "update_reminder":
        arguments = _arguments(
            arguments,
            {
                "id",
                "title",
                "due",
                "list",
                "list_id",
                "notes",
                "priority",
                "flagged",
            },
        )
        payload = {"action": name, "id": _id(arguments)}
        if "title" in arguments:
            payload["title"] = _text(
                arguments["title"], "title", 512, required=True
            )
        if "notes" in arguments:
            payload["notes"] = _text(
                arguments["notes"], "notes", 4096, allow_empty=True
            )
        _list_target(arguments, payload)
        if "priority" in arguments:
            payload["priority"], payload["priority_label"] = _priority(
                arguments["priority"]
            )
        if "due" in arguments:
            payload["due"], payload["due_kind"] = _due(arguments["due"])
        _boolean(arguments, "flagged", payload)
        if len(payload) == 2:
            raise UserError("update_reminder requires at least one field to change")
        return payload

    if name == "set_reminder_completed":
        arguments = _arguments(arguments, {"id", "completed"})
        completed = arguments.get("completed")
        if not isinstance(completed, bool):
            raise UserError("completed must be a boolean")
        return {"action": name, "id": _id(arguments), "completed": completed}

    raise UserError("unknown tool")


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
            timeout=120,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise UserError("Apple Reminders did not respond within 120 seconds")
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
    if not isinstance(result, dict):
        raise UserError("Apple Reminders returned an invalid response")
    return result


def _tool_result(text, structured=None, is_error=False):
    result = {"content": [{"type": "text", "text": text}]}
    if structured is not None:
        result["structuredContent"] = structured
    if is_error:
        result["isError"] = True
    return result


def call_tool(params):
    if not isinstance(params, dict) or params.get("name") not in TOOL_NAMES:
        raise UserError("unknown tool")
    name = params["name"]
    try:
        payload = normalize_arguments(name, params.get("arguments", {}))
        result = invoke_reminders(payload)
    except UserError as error:
        return _tool_result(str(error), is_error=True)

    if name == "list_reminder_lists":
        message = "Found %d reminder lists." % len(result.get("lists", []))
    elif name == "create_reminder_list":
        message = 'Created reminder list “%s”.' % result.get("list", {}).get(
            "name", "Reminders"
        )
    elif name == "rename_reminder_list":
        message = 'Renamed reminder list to “%s”.' % result.get("list", {}).get(
            "name", "Reminders"
        )
    elif name == "search_reminders":
        message = "Found %d matching reminders." % len(result.get("reminders", []))
    elif name == "get_reminder":
        reminder = result.get("reminder", {})
        state = "completed" if reminder.get("completed") else "open"
        message = '“%s” is %s in “%s”.' % (
            reminder.get("title", "Reminder"),
            state,
            reminder.get("list", "Reminders"),
        )
    elif name == "add_reminder":
        reminder = result.get("reminder", {})
        message = 'Added “%s” to “%s”.' % (
            reminder.get("title", "Reminder"),
            reminder.get("list", "Reminders"),
        )
    elif name == "update_reminder":
        message = 'Updated “%s”.' % result.get("reminder", {}).get(
            "title", "reminder"
        )
    elif name == "set_reminder_completed":
        reminder = result.get("reminder", {})
        verb = "Completed" if reminder.get("completed") else "Reopened"
        message = '%s “%s”.' % (verb, reminder.get("title", "reminder"))
    else:
        message = 'Deleted “%s”.' % result.get("deleted", {}).get(
            "title", "reminder"
        )
    return _tool_result(message, result)


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
        return _response(
            message_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {
                    "name": "apple-reminders",
                    "version": SERVER_VERSION,
                },
                "instructions": (
                    "Reads and manages native Apple Reminders. Use read tools to "
                    "resolve exact reminder and list IDs before updating, moving, "
                    "completing, reopening, renaming, or deleting. Relative dates "
                    "must be resolved before calling a tool."
                ),
            },
        )
    if method == "ping":
        return _response(message_id, {})
    if method == "tools/list":
        return _response(message_id, {"tools": TOOLS})
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
            print(
                json.dumps(response, ensure_ascii=False, separators=(",", ":")),
                flush=True,
            )


if __name__ == "__main__":
    main()
