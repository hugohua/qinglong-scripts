const test = require('node:test');
const assert = require('node:assert/strict');

const {
  extractAjaxNonce,
  classifySignResult,
  buildNotification,
  notifyQingLong,
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

test('buildNotification maps success results to a success title', () => {
  assert.deepEqual(
    buildNotification?.({ ok: true, alreadySigned: false, message: '签到成功' }),
    { title: '520switch 签到成功', content: '签到成功' },
  );
});

test('buildNotification maps already-signed results to an already-signed title', () => {
  assert.deepEqual(
    buildNotification?.({ ok: true, alreadySigned: true, message: '今日已签到，请明日再来' }),
    { title: '520switch 今日已签到', content: '今日已签到，请明日再来' },
  );
});

test('buildNotification maps thrown errors to a failure title', () => {
  assert.deepEqual(
    buildNotification?.(new Error('Missing SWITCH520_COOKIE')),
    { title: '520switch 签到失败', content: 'Missing SWITCH520_COOKIE' },
  );
});

test('notifyQingLong forwards title and content to QLAPI.systemNotify', async () => {
  const calls = [];
  const api = {
    async systemNotify(payload) {
      calls.push(payload);
      return { ok: true };
    },
  };

  const result = await notifyQingLong?.(
    { title: '520switch 签到成功', content: '签到成功' },
    api,
  );

  assert.deepEqual(calls, [
    { title: '520switch 签到成功', content: '签到成功' },
  ]);
  assert.deepEqual(result, { ok: true });
});

test('notifyQingLong skips cleanly when QLAPI is unavailable', async () => {
  const result = await notifyQingLong?.(
    { title: '520switch 签到成功', content: '签到成功' },
    undefined,
  );

  assert.equal(result, undefined);
});

test('notifyQingLong does not throw when QLAPI.systemNotify fails', async () => {
  const api = {
    async systemNotify() {
      throw new Error('notify failed');
    },
  };

  const result = await notifyQingLong?.(
    { title: '520switch 签到成功', content: '签到成功' },
    api,
  );

  assert.equal(result, undefined);
});
