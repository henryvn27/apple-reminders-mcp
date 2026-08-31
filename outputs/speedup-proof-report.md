# Apple Reminders search speedup proof

## Result

`search_reminders` now asks Reminders for title/body query candidates before
running the existing JavaScript correctness filters and serializer.

| Candidate | Search result |
| --- | ---: |
| Public baseline `f70deac` | Timed out after 120 seconds |
| Optimized median, 7 runs | 25.571 seconds |
| Optimized p95, 7 runs | 43.398 seconds |

The median speedup is **greater than 4.69x** relative to the baseline timeout
lower bound. The true baseline duration is unknown because the production MCP
timeout intentionally stopped the call at 120 seconds.

## Protocol

- One task-owned temporary Reminders list.
- 24 deterministic reminders with one rare title match.
- Two warmups and seven measured runs for a candidate that can complete.
- 120-second timeout, matching the MCP server's existing user-facing bound.
- Exact ordered IDs checked against the fixture oracle on every completed run.
- Native add, edit, complete, reopen, and delete lifecycle verification.
- Fixture list deletion confirmed before either artifact was accepted.

The baseline could not complete its first warmup within 120 seconds, so the
harness stopped rather than spending six more timeout windows. The optimized
candidate completed all planned warmups and measured runs.

## Correctness boundary

The native query is only a candidate prefilter. The original case-insensitive
title/notes check, completion filter, flag filter, due-date filter, ordering,
pagination, and serialization still run in JavaScript. If native filtering is
unavailable, the bridge falls back to the previous full-list scan.

The regression test covers candidate prefiltering, false-positive removal,
mixed-case matching, result order, and fallback equality. Mutation code and
tool schemas are unchanged.

## Limitations

- Measurements come from one Mac and one macOS/Reminders database state.
- Apple Events are variable; use the full raw sample list, not only the median.
- The baseline is censored at 120 seconds, so only a lower-bound speedup claim
  is valid.
- This benchmark isolates a rare exact-list text query. It does not claim the
  same improvement for unfiltered browsing or queries with many matches.
