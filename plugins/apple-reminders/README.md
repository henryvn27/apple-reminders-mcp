# Apple Reminders

A zero-dependency MCP server for reading and managing the native macOS
Reminders app.

## Tools

| Tool | Effect |
| --- | --- |
| `list_reminder_lists` | Read list names, IDs, and reminder counts |
| `search_reminders` | Read reminders by text, exact list, and completion state |
| `get_reminder` | Read one reminder by exact native ID |
| `add_reminder` | Create one reminder |
| `update_reminder` | Edit or move one exact reminder |
| `set_reminder_completed` | Complete or reopen one exact reminder |
| `delete_reminder` | Permanently delete one exact reminder |

Mutations use exact IDs returned by the read tools. There are no bulk-delete or
list-delete actions. Empty notes clear notes. Existing due values can be changed
within the same all-day or timed kind; cross-kind changes are rejected because
Apple automation can leave stale date state.

## Verify

```bash
cd plugins/apple-reminders
/usr/bin/python3 -m unittest discover -s tests -v
python3 -m py_compile server.py
osacompile -l JavaScript -o /tmp/apple-reminders.scpt reminders.js
```

Tests do not access Reminders. The first live use may trigger a macOS Automation
permission prompt. Allow the calling app to control Reminders. The permission
and reminder data remain machine-local.
