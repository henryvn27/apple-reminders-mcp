# Security

## Boundary

Apple Reminders MCP exposes exactly one non-idempotent write tool. It creates a
reminder after validating the title, due value, list, notes, and priority. It
does not read, edit, complete, or delete reminders.

The server invokes a fixed JXA file through <code>/usr/bin/osascript</code>.
User input is serialized as JSON and passed as a separate process argument; it
is not shell interpolated or executed as source code.

## Reporting a vulnerability

Use [GitHub private vulnerability reporting](https://github.com/henryvn27/apple-reminders-mcp/security/advisories/new).
Please include the affected version, reproduction steps, and expected impact.
Do not open a public issue for an unpatched vulnerability.

## Credentials and data

The plugin requires no API key for local Codex use. Reminders data and macOS
Automation permission remain local. If you use Secure MCP Tunnel, keep its
runtime API key and profile outside this repository.
