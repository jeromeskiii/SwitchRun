# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2026-04-27

### Added
- **Telemetry Module** (`telemetry.py`): Prometheus-compatible metrics collection
  - Routing decision counters with task_id, agent_id, strategy labels
  - Routing latency histograms
  - Model selection tracking
  - Execution result counters
  - Task classification counters
  - Cost estimation gauges
  - MCTS simulation histograms
  - Fallback trigger tracking
- **Health Check Module** (`health.py`): Component health monitoring
  - Classifier health check
  - Router health check
  - Telemetry health check
  - Agents health check
  - Models health check
  - CLI health report command
- **Comprehensive API Documentation** (`API.md`)
  - Full API reference for all modules
  - Code examples for common use cases
  - Configuration options reference
- **Enhanced pyproject.toml**
  - Full project metadata (authors, keywords, classifiers)
  - prometheus-client dependency
  - Optional dev and benchmark dependencies
  - Project URLs (homepage, documentation, repository)
  - Enhanced pytest configuration with markers
- **New CLI Commands**
  - `health` command for component status
  - `version` flag for version information

### Changed
- **README.md**: Enhanced with
  - ASCII art header
  - Architecture diagram
  - Telemetry documentation
  - API documentation reference
- **package.json** (agent-runtime): Enhanced metadata

### Fixed
- **agents.py**: Added None check for `ECOSYSTEM_CONFIG.ports.nexus_core` to prevent AttributeError when ecosystem config is unavailable

## [1.0.0] - 2026-04-20

### Added
- Initial release of Switchboard v2.0.0
- Hybrid Hierarchical Router with 4-layer architecture
  - Layer 1: Intent Classifier (TaskID detection)
  - Layer 2: MCTS Model Router (optional)
  - Layer 3: Execution Planner
  - Layer 4: Execution Engine
- MCTS-based model selection with 12 pre-configured models
- 12 canonical task types with keyword-based classification
- 8 agent targets with specialized capabilities
- Session persistence with append-only JSONL logs
- Permission system with prefix allowlists
- Circuit breaker and rate limiting
- Fallback handling with retry logic
- Comprehensive test suite (100+ tests)

### Components
- `router.py`: Main routing engine
- `classifier.py`: Intent classification
- `planner.py`: Execution plan builder
- `execution.py`: Agent execution with retries
- `mcts_router.py`: MCTS model selection
- `mcts_classifier.py`: MCTS-enhanced classifier
- `hybrid_hierarchical_router.py`: 4-layer hierarchical routing
- `agents.py`: Agent implementations
- `config.py`: Configuration management
- `canonical_ids.py`: TaskID and AgentID enums

[2.0.0]: https://github.com/humansystems/switchboard/releases/tag/v2.0.0
[1.0.0]: https://github.com/humansystems/switchboard/releases/tag/v1.0.0
