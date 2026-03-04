# DateTime Guide

When writing any timestamp (frontmatter `created`/`updated`, progress `last_sync`):

1. Get real time: `date -u +"%Y-%m-%dT%H:%M:%SZ"` (Unix) or `Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ"` (PowerShell)
2. Format: ISO 8601 UTC only (`2024-01-15T14:30:45Z`)
3. Never estimate, never use placeholders like `[Current ISO date/time]`
4. On creates: set both `created` and `updated`
5. On updates: change `updated`, preserve original `created`
6. On syncs: update `last_sync` with current time

Applies to: PRD creation, epic creation, task creation, progress tracking, sync operations,
and any other command that writes timestamps.
