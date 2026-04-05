# Local Browser Auth

DeepScientist can optionally protect the local web workspace with a generated 16-character password.

This protection is local-first:

- it applies to the browser UI
- it also applies to `/api/*` requests from the browser
- it is disabled by default unless you launch with `ds --auth true` or set `ui.auth_enabled: true`

## What Happens On Startup

When you run `ds --auth true`, DeepScientist starts the daemon and prints two important things in the terminal:

- the local browser URL, such as `http://127.0.0.1:20999`
- the generated local access password for that launch

The browser URL is no longer expected to carry `?token=...`.

If the browser is not already authenticated, DeepScientist shows a password modal on top of the landing page before it loads quests, docs, settings, or workspace data.

## How To View The Password

Use either of these:

```bash
ds --status
```

Read the `auth_token` field from the JSON output, or look at the terminal where `ds` was started.

## How Login Persistence Works

After the first successful login:

- the browser stores the local auth state
- later visits from the same browser usually open directly
- restarting or reusing the managed daemon can rotate the password again

If the password rotates, the browser will be asked to log in again.

## How To Disable It

Enable the browser password gate for one launch:

```bash
ds --auth true
```

In that mode:

- the password modal is enabled
- browser requests to `/api/*` require the local auth token

To disable it again explicitly for one launch:

```bash
ds --auth false
```

In that mode:

- the password modal is disabled
- browser requests to `/api/*` do not require the local auth token

## Practical Notes

- This is not intended as internet-grade authentication. It is a local browser gate for machines you control.
- If you share the machine or expose the port remotely, enable auth explicitly.
- If you script against the local daemon from a browser client, authenticate first or disable auth explicitly for that launch.
