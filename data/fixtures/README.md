# FortyGuard response fixtures

Raw JSON responses captured from live API calls on Day 1.

These are the source of truth for `REPLAY_MODE=true`. Commit every successful capture.

Naming convention:
- `{endpoint}_{short_desc}_{YYYYMMDD}.json` for submit responses
- `{endpoint}_{short_desc}_{YYYYMMDD}_result.json` for polled Completed results
- `credit_balance_{YYYYMMDD}.json` for usage meter snapshots

Never commit the full signed `download_link` from heat_intelligence — store the PDF under a short name and redact the URL.
