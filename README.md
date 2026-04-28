# Fusion

Monorepo containing Switchboard (Python) and Agent Runtime (Node.js/TypeScript).

## Packages

- **[packages/switchboard](packages/switchboard/)** — Intelligent LLM routing system. Classifies input, selects optimal models via MCTS, builds execution plans, and routes to 13 specialized agents.
- **[packages/agent-runtime](packages/agent-runtime/)** — Minimal auditable local agent runtime. Provides tool execution (read, glob, bash, routing), session persistence, and a CLI.

## Quick Start

```bash
# Install both packages
make install

# Build
make build

# Run all tests
make test

# Lint
make lint
```

## Environment

Copy `.env.example` to `.env` and fill in API keys:

```bash
cp .env.example .env
```

Set `ECOSYSTEM_ROOT` to this directory:

```bash
export ECOSYSTEM_ROOT=.
```

## Individual Packages

```bash
# Switchboard only
cd packages/switchboard
.venv/bin/python3 -m switchboard --input "write python code"

# Agent Runtime only
cd packages/agent-runtime
npm run build && node dist/index.js run read '{"path":"README.md"}'
```

## Cross-Project Bridge

Agent Runtime calls Switchboard via the `switchboard.route` tool, which spawns `python -m switchboard` as a subprocess. Switchboard calls Agent Runtime via the `AgentRuntimeAgent`, which spawns `node dist/index.js`. Both use `ECOSYSTEM_ROOT` to locate each other.

## License

MIT
