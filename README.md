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
