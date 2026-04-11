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
