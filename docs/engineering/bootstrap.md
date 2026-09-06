# Workspace Bootstrap

This repository is a Python/TypeScript workspace pinned to the accepted
WealthPilot architecture metadata. M00-WP0001-T01 deliberately creates no
application package, route, domain model, migration, or deployment service.

## Toolchain

| Tool | Pinned version | Source of truth |
|---|---:|---|
| Python | `3.12.13` | `.python-version` |
| Node.js LTS | `24.20.0` | `.node-version` |
| uv | `0.11.7` | `pyproject.toml` |
| pnpm | `11.19.0` | `package.json` |

Install the pinned runtimes with the team's runtime manager, then bootstrap
from the committed lockfiles:

```bash
uv sync --frozen
pnpm install --frozen-lockfile
```

The current manifests intentionally contain no runtime dependencies. Future
tasks may add packages only inside their authorized paths and architecture
boundary.

## Architecture verification

Keep a checkout of the Architecture Source of Truth next to this repository:

```text
parent/
├── wealthpilot/
└── wealthpilot-arch/
```

Then run:

```bash
./scripts/verify-architecture-baseline.sh
```

For another local checkout location, pass `--architecture-repo PATH` or set
`WEALTHPILOT_ARCH_REPOSITORY`. The verifier fails closed unless:

- the YAML and JSON baseline records agree;
- both annotated tags peel to the recorded full commit SHAs;
- the accepted addendum commit is the effective architecture commit; and
- the schema blob at that immutable commit has the recorded SHA-256.

## High-conflict ownership

`.github/CODEOWNERS` assigns a single accountable owner to root files, kernel,
contracts, `migrations/env.py`, Compose, generated OpenAPI, and root CI. Task
ownership and reviewer separation remain governed by the Engineering Task
Registry; CODEOWNERS does not authorize work outside an approved task.

Local credentials, `.env` files, personal financial data, and operating-system
metadata are ignored. No real user data or credentials belong in this public
implementation repository.
