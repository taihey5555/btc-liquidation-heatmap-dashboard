# AGENTS.md

## Project Scope

This project is a BTCUSDT liquidation heatmap MVP.

The current implementation prioritizes the visual UI for a dark trading terminal style dashboard using mock data.

## Rules

- Do not break the existing UI.
- Do not add real trading functionality.
- Do not store, request, or expose API keys, credentials, tokens, or any other secrets.
- Use public APIs only when API integration is introduced.
- Always keep the mock data fallback available.
- Reuse existing components and patterns whenever practical.
- Present a plan before making large changes.

## Required Checks

After changes, run:

```bash
npm run build
npm run lint
pytest
```

If a command cannot be run because the required tool or test suite is unavailable, state that clearly in the final response.
