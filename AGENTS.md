# Agent Guide

## Project Scope

This repository stores small Node.js automation scripts that can run:

- locally
- inside QingLong

Keep deliverables simple. Prefer standalone JavaScript files that can run in QingLong without a build step.

## External QingLong Reference

QingLong documentation is available locally at:

- `../qinglong-site` (relative to this repository root)

Treat that repository as the primary reference for QingLong behavior and APIs. Do not copy the whole documentation site into this repository.

When a task involves QingLong integration, check these files first:

- Built-in script APIs: `../qinglong-site/docs/zh/guide/user-guide/built-in-api.mdx`
- Open platform APIs: `../qinglong-site/docs/zh/api/open.mdx`
- Other REST API docs: `../qinglong-site/docs/zh/api/`

## Working Rules

- If a script only needs one or two QingLong capabilities, document the dependency in `docs/references/qinglong.md`.
- Prefer narrow test doubles over a full QingLong mock implementation.
- Only introduce a shared QingLong adapter or larger mock layer when multiple scripts need the same behavior.
- Keep references to upstream docs explicit so later updates can be checked against source files.

## Current QingLong Usage

The current script usage is intentionally small:

- runtime environment variables provided by QingLong
- optional `globalThis.QLAPI.systemNotify(...)` when available

If future work expands beyond this, update `docs/references/qinglong.md` first before adding abstractions.
