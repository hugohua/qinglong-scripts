# 520switch Node.js Auto Sign-In Design

## Goal

Create a small local Node.js project that performs the daily sign-in request for `www.520switch.com` using a login cookie provided through `.env`.

## Scope

In scope:

- Read `COOKIE` from `.env`
- Fetch a site page to obtain the current `zb.ajax_nonce`
- Submit the sign-in request to `https://www.520switch.com/wp-admin/admin-ajax.php`
- Print a clear terminal result
- Return exit code `0` for success and already-signed cases
- Return exit code `1` for configuration, parsing, authentication, or network failures

Out of scope:

- Browser automation
- Login flow automation
- Scheduled task setup such as `cron`
- Multi-account support

## Request Contract

The captured sign-in flow uses:

- Method: `POST`
- URL: `https://www.520switch.com/wp-admin/admin-ajax.php`
- Content-Type: `application/x-www-form-urlencoded; charset=UTF-8`
- Body:
  - `action=zb_user_qiandao`
  - `nonce=<current zb.ajax_nonce>`

The request depends on a valid logged-in cookie and a fresh nonce taken from a site page that defines:

```js
var zb = { ..., "ajax_nonce": "..." }
```

## Runtime Flow

1. Load environment variables from `.env`.
2. Validate that `COOKIE` is present and non-empty.
3. Request the homepage with the provided cookie and a normal browser-like `User-Agent`.
4. Extract `zb.ajax_nonce` from the HTML response.
5. Submit the sign-in form body with the same cookie and required headers.
6. Parse the JSON response and map it to CLI output and exit codes.

## Project Structure

- `package.json`: project metadata and scripts
- `.env.example`: sample environment file with `COOKIE=`
- `src/index.js`: CLI entrypoint and process exit handling
- `src/config.js`: environment loading and validation
- `src/sign.js`: page fetch, nonce extraction, sign-in request, result mapping
- `README.md`: setup and usage

## Result Handling

Successful sign-in:

- Response shape is expected to include `status: 1`
- Script prints the returned message
- Process exits with `0`

Already signed:

- Response shape is expected to include `status: 0` with a message such as `今日已签到，请明日再来`
- Script treats this as a non-error terminal state
- Process exits with `0`

Failure cases:

- Missing `.env` or missing `COOKIE`
- Page fetch fails
- Nonce cannot be extracted from the page
- Sign-in response is non-JSON or does not match the expected shape
- Server indicates the cookie is invalid or the request is rejected
- Process exits with `1`

## Headers

The implementation should send only headers that are materially useful:

- `User-Agent`
- `Cookie`
- `Content-Type: application/x-www-form-urlencoded; charset=UTF-8`
- `Origin: https://www.520switch.com`
- `Referer: https://www.520switch.com/`
- `X-Requested-With: XMLHttpRequest`
- `Accept: application/json, text/javascript, */*; q=0.01`

It should not attempt to replay browser-only pseudo headers such as `:authority`.

## Testing Strategy

The project should include behavior-focused tests that cover:

- extracting `ajax_nonce` from representative HTML
- handling a success response
- handling an already-signed response
- surfacing a missing nonce as an error

To keep the implementation simple, parsing and response mapping logic should be written in a way that can be tested without live network calls. The live sign-in command remains a manual integration test because it requires a real account cookie.

## Assumptions

- The user runs Node.js 18 or newer so native `fetch` is available.
- The site continues to expose `zb.ajax_nonce` in page HTML.
- The provided cookie is copied from an already-authenticated browser session.

## Acceptance Criteria

- Running `npm install` then `npm start` works in a fresh checkout after filling `.env`.
- The script signs in successfully when the cookie is valid and the account has not signed in yet.
- The script exits cleanly with code `0` when the account has already signed in for the day.
- The script fails with a clear error message when the cookie is missing, invalid, or the nonce cannot be found.
