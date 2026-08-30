# Security

## Boundary

Apple Reminders MCP exposes three read tools and four mutation tools. Read tools
can list native list metadata and return reminder contents. Mutations create one
reminder or target one exact native reminder ID returned by a read tool.

The server does not expose bulk deletion or list deletion. The delete tool is
marked destructive, add and delete are marked non-idempotent, and read tools are
marked read-only. These annotations let compatible MCP clients apply the right
confirmation policy.

The server invokes a fixed JXA file through `/usr/bin/osascript`. User input is
serialized as JSON and passed as a separate process argument; it is not shell
interpolated or executed as source code. Inputs reject unknown fields, null
bytes, oversized strings, ambiguous list names, invalid dates, and mutations
without an exact reminder ID.

## Data access

Read tools can return reminder titles, notes, due values, priorities, completion
state, list names, and native IDs to the calling MCP client. Local Codex use
requires no API key and sends nothing to this project. When using a remote MCP
tunnel, the tunnel provider and calling client are part of your data boundary.

macOS Automation permission and Reminders data remain on the Mac unless the
calling client or a user-configured tunnel transmits the returned data.

## Reporting a vulnerability

Use [GitHub private vulnerability reporting](https://github.com/henryvn27/apple-reminders-mcp/security/advisories/new).
Include the affected version, reproduction steps, and expected impact. Do not
open a public issue for an unpatched vulnerability.

## Credentials

The plugin requires no credential for local Codex use. If you use Secure MCP
Tunnel, keep its runtime API key and profile outside this repository.
