# CLAUDE.md

This file gives AI agents a repo-level overview and working rules. Keep implementation details in module-level `README.md` files, `docs/`, and the code itself.

## Project Overview

This repository contains a complex event processing system for quantitative trading. At a high level, it ingests market and portfolio data, evaluates rules and triggers, emits signals, and supports downstream actions such as rebalancing and external integrations.

## Main Areas

| Path | Responsibility |
|---|---|
| `cep/core/` | Shared eventing, context, and foundational primitives |
| `cep/engine/` | Rule evaluation and execution logic |
| `cep/triggers/` | Trigger definitions that observe events and emit signals |
| `rebalance/` | Rebalance workflows and related domain logic |
| `nlp/` | Natural-language rule parsing |
| `adapters/` | Integrations with external systems and services |
| `frontend/` | Web-facing UI and API surfaces |

## Architectural Principles

- Prefer event-driven flows and loose coupling between components.
- Keep triggers focused on detection and signal emission, not downstream business actions.
- Use dependency injection for shared services and runtime configuration.
- Treat events and shared state transitions carefully; avoid hidden side effects and implicit global state.
- Preserve module boundaries: core primitives should stay generic, and adapter-specific concerns should remain at the edges.

## Working Expectations for Agents

- Start with the nearest relevant documentation: the local `README.md`, related files in `docs/`, and the surrounding code.
- Make changes in the most specific module that owns the behavior instead of centralizing special cases.
- If you add or change behavior, update the closest documentation that explains that behavior.
- Prefer small, consistent changes that fit the existing architecture and naming patterns.
- Add or update tests. A bug fix should generally come with test coverage that fails before your change and passes afterwards. 100% coverage is not required, but aim for meaningful assertions.
- Do not duplicate implementation details here; if more explanation is needed, add it near the owning module.

## Coding Guidelines

- Run `ruff` and `pyright` before considering Python changes complete, and address all reported issues.
- Keep new code typed, readable, and consistent with existing patterns in the touched module.
- Avoid introducing module-level singletons or tightly coupled cross-module shortcuts unless the existing design explicitly requires them.
- When changing public behavior, tests and docs should move with the code.
