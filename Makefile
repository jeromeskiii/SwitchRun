.PHONY: install switchboard-install agent-install build switchboard-build agent-build \
       test switchboard-test agent-test lint switchboard-lint agent-lint clean

# ── Install ──────────────────────────────────────────────────
install: switchboard-install agent-install

switchboard-install:
	cd packages/switchboard && python3 -m venv .venv && \
		.venv/bin/pip install --upgrade pip --quiet && \
		.venv/bin/pip install -e ".[dev]" --quiet

agent-install:
	cd packages/agent-runtime && npm ci --silent

# ── Build ────────────────────────────────────────────────────
build: switchboard-build agent-build

switchboard-build:
	cd packages/switchboard && .venv/bin/pip install -e . --quiet

agent-build:
	cd packages/agent-runtime && npm run build

# ── Test ─────────────────────────────────────────────────────
test: switchboard-test agent-test

switchboard-test:
	cd packages/switchboard && .venv/bin/pytest -q

agent-test:
	cd packages/agent-runtime && npm test

# ── Lint ─────────────────────────────────────────────────────
lint: switchboard-lint agent-lint

switchboard-lint:
	cd packages/switchboard && .venv/bin/ruff check .
	cd packages/switchboard && .venv/bin/pyright

agent-lint:
	cd packages/agent-runtime && npm run typecheck

# ── Clean ────────────────────────────────────────────────────
clean:
	rm -rf packages/switchboard/.venv packages/switchboard/__pycache__
	rm -rf packages/switchboard/switchboard.egg-info packages/switchboard/.pytest_cache
	rm -rf packages/agent-runtime/dist packages/agent-runtime/node_modules
	find . -name ".DS_Store" -delete
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
