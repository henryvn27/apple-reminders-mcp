# Apple Reminders

A zero-dependency MCP server for reading and managing the native macOS
Reminders app.

## Tools

| Tool | Effect |
| --- | --- |
| `list_reminder_lists` | Read list names, IDs, and reminder counts |
| `create_reminder_list` | Create one list in the default account |
| `rename_reminder_list` | Rename one exact list by native ID |
| `search_reminders` | Read and paginate reminders by text, list, completion, flag, and local due-date range |
| `get_reminder` | Read one reminder by exact native ID |
| `add_reminder` | Create one reminder |
| `update_reminder` | Edit, flag, or move one exact reminder |
| `set_reminder_completed` | Complete or reopen one exact reminder |
| `delete_reminder` | Permanently delete one exact reminder |

Reads include flags, alert time, creation/modification timestamps, completion
metadata, notes, priority, due value, and list identity. Mutations use exact IDs
returned by the read tools, and list IDs can target searches, adds, and moves.

There are no bulk-delete or list-delete actions. Empty notes clear notes.
Existing due values can be changed within the same all-day or timed kind;
cross-kind changes and due clearing are not exposed because Apple automation
can leave stale date state or reject the missing-date value. Timed due dates
create the native alert; alert time is readable but not a separate writer.

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
