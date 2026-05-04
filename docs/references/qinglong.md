# QingLong Reference

This file records the QingLong documentation that this repository relies on, without vendoring the full doc site.

## Upstream Source

- Local reference repo: `../qinglong-site` (relative to this repository root)
- Upstream repository: `https://github.com/whyour/qinglong-site`
- Local snapshot checked on: `2026-04-12`
- Local snapshot commit: `aa3bbeb`

## Primary Documents

### Built-in Script API

Source:

- `../qinglong-site/docs/zh/guide/user-guide/built-in-api.mdx`

Relevant point for this repository:

- QingLong exposes a global `QLAPI` object inside supported script runtimes.
- `QLAPI.systemNotify` accepts:
  - `title: string`
  - `content: string`
  - optional `notificationInfo: object`

Current project usage:

- `520switch-signin.py` uses `QLAPI.systemNotify` if it exists.
- If `QLAPI` is missing, the script should continue without treating that as a failure.

### Environment Variable Updates

Source:

- `../qinglong-site/docs/zh/guide/user-guide/built-in-api.mdx`

Relevant points for this repository:

- `QLAPI.getEnvs({ searchValue })` returns QingLong environment variables matching a name or search value.
- `QLAPI.updateEnv({ env })` updates an existing environment variable.
- `QLAPI.createEnv({ envs })` creates new environment variables.

Current project usage:

- `520switch-signin.py` updates or creates `SWITCH520_COOKIE` after a successful captcha login.
- The script uses only the narrow `getEnvs` / `updateEnv` / `createEnv` subset and should continue when `QLAPI` is unavailable, such as during local runs.

### Open Platform API

Source:

- `../qinglong-site/docs/zh/api/open.mdx`

Use this document only when the repository starts interacting with QingLong applications, tokens, or other open platform endpoints. It is not needed for the current sign-in script.

## Repository Policy

- Do not import the full QingLong documentation site into this repository.
- Keep this file as a concise dependency summary and point back to the upstream source paths.
- If a new script depends on another QingLong method, add the method name and source file here.

## Mocking Guidance

Do not build a full mock `QLAPI` by default.

Preferred order:

1. Pass a minimal fake object directly in tests.
2. Extract a small shared adapter only if multiple scripts need the same QingLong method.
3. Build a larger mock layer only when several methods are used and duplicated test setup becomes expensive.

For the current repository, a minimal fake object with `systemNotify()` is sufficient.
