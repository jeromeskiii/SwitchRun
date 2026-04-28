# Contributing Guide (Agents)

This guide is for autonomous agents editing `agent-runtime`.

## Scope Discipline

- Work only in `/Users/jm1/agent-runtime`.
- Do not modify external repos unless explicitly requested.
- Keep changes within the user’s stated goal.

## Required Checks

Run after code changes:

```bash
npm run typecheck
npm run build
```

If a check fails, do not report completion until fixed or explicitly documented as out-of-scope.

## Editing Rules

- Use explicit, minimal edits.
- Keep CLI command output JSON-stable where possible.
- Prefer additive changes over risky rewrites unless requested.
- Update `README.md` when CLI usage changes.
- Update `docs/architecture.md` when architecture boundaries change.

## Startup Module Contract

- `entrypoint.ts`: entrypoint mode detection/initialization.
- `settings-loader.ts`: eager startup flag parsing.
- `pending-connections.ts`: early intent detection.
- `prefetch.ts`: deferred startup prefetch utilities.

Do not leak startup concerns into tools or session store.

## Session Store Contract

- Session logs are JSONL.
- Snapshots are JSON metadata.
- Export/import format must remain versioned.
- New fields must be backward-compatible.

## Response Contract

When handing off:
- summarize what changed,
- list files touched,
- include exact verify commands,
- call out residual risks if any.

