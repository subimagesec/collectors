# Agent guide

This repository holds open source collectors. Each one runs in a customer's own
environment, reads a system that only that environment can reach or that needs
a credential the customer keeps, and writes a JSON snapshot to a file or a
bucket the customer owns. A security graph then ingests the snapshot:

- [Cartography](https://github.com/cartography-cncf/cartography), the open
  source graph, reads snapshots with its report-source modules (for example,
  `--onepassword-source`).
- [Subimage](https://subimage.io) runs managed Cartography and reads the same
  snapshots from the customer's bucket. Subimage adds parallel syncs, hardened
  per-tenant infrastructure, attack paths, and an AI analyst on top of the
  graph, and maintains these collectors.

The collector is the only component that touches the source credential. Keep
it that way: a consumer gets read access to the snapshot, never to the source.

## Layout

| Path | What it holds |
| --- | --- |
| [`1password/`](1password/) | 1Password collector: source, schema, tests, container, deployment examples. See [`1password/AGENTS.md`](1password/AGENTS.md). |
| `.github/workflows/` | CI for every collector, container builds, and tag-driven releases. |
| `Makefile` | Runs `test`, `test_lint`, and `test_unit` in every collector directory. |

Each collector owns its runtime, dependencies, schema, docs, examples, and
release cycle. Do not share code between collectors.

## Commands

```sh
make test                 # lint and tests for every collector
cd 1password && make test # one collector
```

Use `uv run --frozen` for Python. CI runs the same Make targets.

## Rules

- **This repository is public.** Never commit customer names, account or vault
  IDs, tokens, captured provider responses, or real snapshots. Test data is
  synthetic and uses canary values to prove secrets never leak.
- **Never export secret values.** A collector reads metadata only. A field that
  could carry secret material stays out of the snapshot unless it is opt-in and
  documented. Names and titles that make the graph readable, such as 1Password
  vault names and item titles, are collected by default and have a documented
  opt-out (`--omit-titles`).
- **Keep credentials out of arguments, logs, and errors.** Pass them through
  the environment. Error messages are generic and never echo provider output.
- **Fail closed.** A collector publishes only a complete, validated snapshot.
  Any failed read exits non-zero and leaves the previous snapshot in place.
- **Collectors run once and exit.** Scheduling belongs to the platform:
  EventBridge Scheduler, Cloud Scheduler, a Kubernetes CronJob, or similar. Each
  collector ships examples for these.
- **Snapshot formats are contracts.** Version them with a JSON schema. Additive
  changes bump the minor version; anything a consumer must handle differently
  bumps the major version and needs a matching consumer change.
- Write docs in the [Google developer documentation style](https://developers.google.com/style):
  present tense, active voice, short sentences.

## Releases

A collector releases from `main` when a maintainer pushes a tag such as
`1password/v0.1.1`. The tag must match the version in the collector's
`pyproject.toml`. The release workflow checks this, runs the collector's CI,
and publishes a multi-architecture image to
`ghcr.io/subimagesec/collectors/<collector>`. Release tags are immutable.
