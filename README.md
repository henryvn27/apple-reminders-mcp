<p align="center">
  <img src="assets/social-preview.png" alt="Apple Reminders MCP — Tell your AI. It’s on your list." width="100%">
</p>

<h1 align="center">Apple Reminders MCP</h1>

<p align="center"><strong>Tell your AI. It’s on your list.</strong></p>

<p align="center">
  <a href="https://github.com/henryvn27/apple-reminders-mcp/actions/workflows/ci.yml"><img src="https://github.com/henryvn27/apple-reminders-mcp/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-1a1a1a.svg" alt="MIT License"></a>
  <img src="https://img.shields.io/badge/macOS-native-f5b700.svg" alt="Native macOS">
  <img src="https://img.shields.io/badge/dependencies-0-f4eee3.svg" alt="Zero dependencies">
</p>

A tiny, local-first MCP plugin that gives Codex or ChatGPT one carefully scoped
power: create a reminder in the native macOS Reminders app.

~~~text
You: Remind me to submit the form tomorrow at 4 PM.
AI: Added “Submit the form” to the “Reminders” list.
~~~

No cloud database. No new task app. No dependency install.

## Install in Codex

~~~bash
codex plugin marketplace add henryvn27/apple-reminders-mcp
codex plugin add apple-reminders@apple-reminders-mcp
~~~

Start a new Codex task after installation, then ask naturally:

~~~text
Remind me next Friday at 3 PM to send the Scoutly build.
Add “bring goggles” to my School list with high priority.
Remind me on September 12 to renew the domain. Note: check the card first.
~~~

macOS may ask whether Codex or Python can control Reminders on the first write.
Choose **Allow**. The permission and your reminder data stay on your Mac.

## What it can do

| Input | Support |
| --- | --- |
| Title | Required |
| Due date | All-day <code>YYYY-MM-DD</code> |
| Due time | ISO 8601 with an explicit UTC offset |
| List | Exact Reminders list name |
| Notes | Up to 4,096 characters |
| Priority | None, low, medium, or high |

It intentionally cannot read, complete, edit, or delete reminders. One tool,
one direction, easy to trust.

## How it works

~~~mermaid
flowchart LR
    A[Codex or ChatGPT] -->|add_reminder| B[MCP server]
    B --> C[Strict Python validation]
    C -->|fixed argv JSON| D[macOS automation]
    D --> E[Apple Reminders]
~~~

The MCP server uses Python's standard library and invokes a fixed JavaScript
for Automation bridge. User content is passed as JSON in a separate process
argument—never interpolated into shell code.

## ChatGPT

ChatGPT cannot call a local stdio MCP process directly. OpenAI's
[Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)
can expose this same server through an outbound-only connection when your plan
and workspace support developer-mode write actions.

~~~bash
export CONTROL_PLANE_API_KEY="<runtime API key>"
tunnel-client init \
  --sample sample_mcp_stdio_local \
  --profile apple-reminders \
  --tunnel-id "<tunnel_id>" \
  --mcp-command "/usr/bin/python3 /absolute/path/to/apple-reminders-mcp/plugins/apple-reminders/server.py"
tunnel-client doctor --profile apple-reminders --explain
tunnel-client run --profile apple-reminders
~~~

Never commit the runtime API key or tunnel profile. See OpenAI's
[current full-MCP availability](https://help.openai.com/en/articles/12584461-developer-mode-and-full-mcp-connectors-in-chatgpt)
before setup.

## Develop

~~~bash
cd plugins/apple-reminders
/usr/bin/python3 -m unittest discover -s tests -v
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  | /usr/bin/python3 server.py
~~~

Tests never write to Reminders. Live writes only happen through
<code>tools/call</code>.

## Security

Please report vulnerabilities through
[GitHub private vulnerability reporting](https://github.com/henryvn27/apple-reminders-mcp/security/advisories/new).
The full security boundary is documented in [SECURITY.md](SECURITY.md).

## License

MIT © Henry Van Ness

Apple and Reminders are trademarks of Apple Inc. This project is independent
and is not affiliated with or endorsed by Apple.
