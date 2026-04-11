# 520switch QingLong Sign-In Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a QingLong-compatible single-file Node.js sign-in script for `www.520switch.com` that can read `COOKIE` from task environment variables or a local `.env` file.

**Architecture:** Keep the runtime deliverable as one executable script, `520switch-signin.js`, with small internal helper functions for environment loading, nonce extraction, request submission, and response classification. Use Node 18+ built-ins only, and expose helpers through `module.exports` so the same logic can be tested with the built-in `node:test` runner without introducing external dependencies.

**Tech Stack:** Node.js 18+, native `fetch`, built-in `node:test`, CommonJS modules, plain Markdown docs

---

## File Map

- Create: `520switch-signin.js`
  Responsibility: executable QingLong-compatible script with env loading, nonce extraction, sign-in request, CLI output, exit code handling, and exported helpers for tests.
- Create: `tests/520switch-signin.test.js`
  Responsibility: behavior tests for nonce extraction, success classification, already-signed classification, and missing-nonce failure.
- Create: `package.json`
  Responsibility: local project metadata and scripts for `start` and `test`.
- Create: `.env.example`
  Responsibility: sample configuration for local runs.
- Create: `README.md`
  Responsibility: local usage, QingLong deployment notes, and environment variable instructions.

### Task 1: Scaffold the project metadata and test harness

**Files:**
- Create: `package.json`
- Create: `.env.example`

- [ ] **Step 1: Write the project metadata**

```json
{
  "name": "qinlong",
  "version": "1.0.0",
  "private": true,
  "description": "520switch QingLong sign-in script",
  "main": "520switch-signin.js",
  "scripts": {
    "start": "node 520switch-signin.js",
    "test": "node --test"
  },
  "engines": {
    "node": ">=18"
  }
}
```

- [ ] **Step 2: Write the sample environment file**

```dotenv
COOKIE=
```

- [ ] **Step 3: Verify the files exist with expected content**

Run: `sed -n '1,120p' /Users/hugo/github/qinlong/package.json && sed -n '1,20p' /Users/hugo/github/qinlong/.env.example`
Expected: `package.json` shows the `start` and `test` scripts, and `.env.example` contains a single `COOKIE=` entry.

- [ ] **Step 4: Commit the scaffold**

```bash
git add /Users/hugo/github/qinlong/package.json /Users/hugo/github/qinlong/.env.example
git commit -m "chore: scaffold qinglong sign-in project"
```

### Task 2: Write failing tests for the single-file script helpers

**Files:**
- Create: `tests/520switch-signin.test.js`
- Test: `tests/520switch-signin.test.js`

- [ ] **Step 1: Write the failing tests**

```js
const test = require('node:test');
const assert = require('node:assert/strict');

const {
  extractAjaxNonce,
  classifySignResult,
} = require('../520switch-signin');

test('extractAjaxNonce reads ajax_nonce from zb config', () => {
  const html = `
    <script>
      var zb = {"home_url":"https://www.520switch.com","ajax_nonce":"46fa70a40e"};
    </script>
  `;

  assert.equal(extractAjaxNonce(html), '46fa70a40e');
});

test('extractAjaxNonce throws when ajax_nonce is missing', () => {
  assert.throws(
    () => extractAjaxNonce('<html><body>missing nonce</body></html>'),
    /ajax_nonce/i,
  );
});

test('classifySignResult treats status 1 as success', () => {
  assert.deepEqual(
    classifySignResult({ status: 1, msg: '签到成功' }),
    { ok: true, alreadySigned: false, message: '签到成功' },
  );
});

test('classifySignResult treats already signed as non-error', () => {
  assert.deepEqual(
    classifySignResult({ status: 0, msg: '今日已签到，请明日再来' }),
    { ok: true, alreadySigned: true, message: '今日已签到，请明日再来' },
  );
});

test('classifySignResult rejects unexpected failure responses', () => {
  assert.throws(
    () => classifySignResult({ status: 0, msg: '请先登录' }),
    /请先登录/,
  );
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `node --test /Users/hugo/github/qinlong/tests/520switch-signin.test.js`
Expected: FAIL because `../520switch-signin` does not exist yet.

- [ ] **Step 3: Commit the failing tests**

```bash
git add /Users/hugo/github/qinlong/tests/520switch-signin.test.js
git commit -m "test: add sign-in script behavior tests"
```

### Task 3: Implement the QingLong-compatible single-file script

**Files:**
- Create: `520switch-signin.js`
- Modify: `tests/520switch-signin.test.js`
- Test: `tests/520switch-signin.test.js`

- [ ] **Step 1: Write the minimal implementation**

```js
#!/usr/bin/env node

const fs = require('node:fs');
const path = require('node:path');

const HOME_URL = 'https://www.520switch.com/';
const AJAX_URL = 'https://www.520switch.com/wp-admin/admin-ajax.php';
const USER_AGENT =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36';

function parseDotEnv(text) {
  const result = {};
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith('#')) continue;
    const eqIndex = line.indexOf('=');
    if (eqIndex === -1) continue;
    const key = line.slice(0, eqIndex).trim();
    let value = line.slice(eqIndex + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    result[key] = value;
  }
  return result;
}

function loadCookie() {
  if (process.env.COOKIE && process.env.COOKIE.trim()) {
    return process.env.COOKIE.trim();
  }

  const candidates = [
    path.resolve(process.cwd(), '.env'),
    path.resolve(__dirname, '.env'),
  ];

  for (const filePath of candidates) {
    if (!fs.existsSync(filePath)) continue;
    const env = parseDotEnv(fs.readFileSync(filePath, 'utf8'));
    if (env.COOKIE && env.COOKIE.trim()) {
      return env.COOKIE.trim();
    }
  }

  throw new Error('Missing COOKIE. Set process.env.COOKIE or add it to .env');
}

function extractAjaxNonce(html) {
  const scriptMatch = html.match(/var\\s+zb\\s*=\\s*(\\{[\\s\\S]*?\\});/);
  if (!scriptMatch) {
    throw new Error('Unable to find zb config in HTML');
  }

  let config;
  try {
    config = JSON.parse(scriptMatch[1]);
  } catch (error) {
    throw new Error(`Unable to parse zb config JSON: ${error.message}`);
  }

  if (!config.ajax_nonce) {
    throw new Error('Unable to find ajax_nonce in zb config');
  }

  return String(config.ajax_nonce);
}

function classifySignResult(payload) {
  const message = typeof payload?.msg === 'string' ? payload.msg : 'Unknown response';

  if (payload?.status === 1) {
    return { ok: true, alreadySigned: false, message };
  }

  if (payload?.status === 0 && /已签到|明日再来/.test(message)) {
    return { ok: true, alreadySigned: true, message };
  }

  throw new Error(message);
}

async function fetchNonce(cookie) {
  const response = await fetch(HOME_URL, {
    headers: {
      'User-Agent': USER_AGENT,
      Accept: 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
      Cookie: cookie,
    },
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch homepage: ${response.status} ${response.statusText}`);
  }

  return extractAjaxNonce(await response.text());
}

async function signIn(cookie, nonce) {
  const body = new URLSearchParams({
    action: 'zb_user_qiandao',
    nonce,
  });

  const response = await fetch(AJAX_URL, {
    method: 'POST',
    headers: {
      'User-Agent': USER_AGENT,
      Accept: 'application/json, text/javascript, */*; q=0.01',
      'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
      Origin: 'https://www.520switch.com',
      Referer: HOME_URL,
      'X-Requested-With': 'XMLHttpRequest',
      Cookie: cookie,
    },
    body,
  });

  const text = await response.text();
  let payload;

  try {
    payload = JSON.parse(text);
  } catch (error) {
    throw new Error(`Unexpected non-JSON response: ${text.slice(0, 200)}`);
  }

  return classifySignResult(payload);
}

async function main() {
  const cookie = loadCookie();
  const nonce = await fetchNonce(cookie);
  const result = await signIn(cookie, nonce);
  console.log(result.message);
}

if (require.main === module) {
  main().catch((error) => {
    console.error(error.message);
    process.exitCode = 1;
  });
}

module.exports = {
  parseDotEnv,
  loadCookie,
  extractAjaxNonce,
  classifySignResult,
  fetchNonce,
  signIn,
  main,
};
```

- [ ] **Step 2: Run the tests to verify they pass**

Run: `node --test /Users/hugo/github/qinlong/tests/520switch-signin.test.js`
Expected: PASS with all five tests green.

- [ ] **Step 3: Manually verify the CLI configuration failure path**

Run: `env -i PATH="$PATH" node /Users/hugo/github/qinlong/520switch-signin.js`
Expected: exits with code `1` and prints `Missing COOKIE...`

- [ ] **Step 4: Commit the script implementation**

```bash
git add /Users/hugo/github/qinlong/520switch-signin.js /Users/hugo/github/qinlong/tests/520switch-signin.test.js
git commit -m "feat: add qinglong-compatible sign-in script"
```

### Task 4: Document local and QingLong usage

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write the README**

```md
# 520switch Sign-In Script

## Requirements

- Node.js 18+

## Local Usage

1. Copy `.env.example` to `.env`
2. Fill `COOKIE=...`
3. Run `npm start`

## QingLong Usage

1. Upload `520switch-signin.js` to QingLong's scripts directory
2. Create an environment variable named `COOKIE`
3. Create a task such as:

```bash
task /ql/data/scripts/520switch-signin.js
```

or:

```bash
node /ql/data/scripts/520switch-signin.js
```

## Behavior

- Success: prints the success message and exits `0`
- Already signed: prints the site message and exits `0`
- Failure: prints an error and exits `1`
```

- [ ] **Step 2: Verify the README and package script**

Run: `sed -n '1,220p' /Users/hugo/github/qinlong/README.md && npm --prefix /Users/hugo/github/qinlong run test`
Expected: README shows local and QingLong instructions, and the test suite remains green.

- [ ] **Step 3: Commit the documentation**

```bash
git add /Users/hugo/github/qinlong/README.md
git commit -m "docs: add usage instructions"
```
