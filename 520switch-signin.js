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
    if (!line || line.startsWith('#')) {
      continue;
    }

    const eqIndex = line.indexOf('=');
    if (eqIndex === -1) {
      continue;
    }

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
  if (process.env.SWITCH520_COOKIE && process.env.SWITCH520_COOKIE.trim()) {
    return process.env.SWITCH520_COOKIE.trim();
  }

  const candidates = [
    path.resolve(process.cwd(), '.env'),
    path.resolve(__dirname, '.env'),
  ];

  for (const filePath of candidates) {
    if (!fs.existsSync(filePath)) {
      continue;
    }

    const env = parseDotEnv(fs.readFileSync(filePath, 'utf8'));
    if (env.SWITCH520_COOKIE && env.SWITCH520_COOKIE.trim()) {
      return env.SWITCH520_COOKIE.trim();
    }
  }

  throw new Error('Missing SWITCH520_COOKIE. Set process.env.SWITCH520_COOKIE or add it to .env');
}

function extractAjaxNonce(html) {
  const scriptMatch = html.match(/var\s+zb\s*=\s*(\{[\s\S]*?\});/);
  if (!scriptMatch) {
    throw new Error('Unable to find ajax_nonce: missing zb config in HTML');
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
    return {
      ok: true,
      alreadySigned: false,
      message,
    };
  }

  if (payload?.status === 0 && /已签到|明日再来/.test(message)) {
    return {
      ok: true,
      alreadySigned: true,
      message,
    };
  }

  throw new Error(message);
}

function buildNotification(resultOrError) {
  if (resultOrError instanceof Error) {
    return {
      title: '520switch 签到失败',
      content: resultOrError.message,
    };
  }

  if (resultOrError?.ok && resultOrError.alreadySigned) {
    return {
      title: '520switch 今日已签到',
      content: resultOrError.message,
    };
  }

  if (resultOrError?.ok) {
    return {
      title: '520switch 签到成功',
      content: resultOrError.message,
    };
  }

  return {
    title: '520switch 签到失败',
    content: String(resultOrError?.message ?? 'Unknown response'),
  };
}

async function notifyQingLong(payload, api = globalThis.QLAPI) {
  if (!api || typeof api.systemNotify !== 'function') {
    return undefined;
  }

  try {
    return await api.systemNotify(payload);
  } catch {
    return undefined;
  }
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

  const html = await response.text();
  return extractAjaxNonce(html);
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
  } catch {
    throw new Error(`Unexpected non-JSON response: ${text.slice(0, 200)}`);
  }

  return classifySignResult(payload);
}

async function main() {
  const cookie = loadCookie();
  const nonce = await fetchNonce(cookie);
  const result = await signIn(cookie, nonce);
  console.log(result.message);
  await notifyQingLong(buildNotification(result));
  return result;
}

async function runCli() {
  try {
    await main();
  } catch (error) {
    const normalizedError = error instanceof Error ? error : new Error(String(error));
    console.error(normalizedError.message);
    await notifyQingLong(buildNotification(normalizedError));
    process.exitCode = 1;
  }
}

if (require.main === module) {
  runCli();
}

module.exports = {
  parseDotEnv,
  loadCookie,
  extractAjaxNonce,
  classifySignResult,
  buildNotification,
  notifyQingLong,
  fetchNonce,
  signIn,
  main,
  runCli,
};
