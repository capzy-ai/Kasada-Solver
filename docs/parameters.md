# Parameters reference — Kasada Bot Defense

Every field you can pass to `POST /createTask` for this task type.

## Envelope

```json
{
  "clientKey": "capzy_xxxxxxxxxxxxxxxxxxxxxxxx",
  "task": { ... }
}
```

| Field        | Required | Notes                                                       |
|--------------|:--------:|-------------------------------------------------------------|
| `clientKey`  | yes      | Your Capzy API key. Starts with `capzy_`. Find it at [capzy.ai/dashboard/api-keys](https://capzy.ai/dashboard/api-keys). |
| `task`       | yes      | The task object — see below.                                |

## Task object

### Required + optional fields

| Field | Type | Required | Notes |
|-------|------|:--------:|-------|
| `type` | `string` | yes | `KasadaCaptchaTaskProxyLess` / `KasadaCaptchaTask` (browser solve → CT, CD when available), or **`KasadaCaptchaCDTask`** (browserless `x-kpsdk-cd` generator — you pass `site`/`s`/`ct`/`st`/`fc`, we compute the PoW natively; see [the CD section below](#kasadacaptchacdtask--browserless-cd-generator)) |
| `websiteURL` | `string` | yes | The Kasada-protected URL you want tokens for. Can be an HTML page **or** a JSON/GraphQL API endpoint (e.g. `https://api.example.com/graphql`). Accepted aliases: `pageURL`, `websiteUrl`. |
| `bootstrapURL` | `string` | no | Page to load in order to arm the Kasada SDK when `websiteURL` is an API endpoint. By default we derive it: an `api.`/`gateway.` subdomain maps to the brand's `www` site (e.g. `api.example.com` → `https://www.example.com/`), and a path-based API on an ordinary host uses that host's root. Set this explicitly if the derived page doesn't serve the challenge. |
| `pjsUrl` | `string` | no | The Kasada SDK script URL (`p.js` / `ips.js`) — **not** your API endpoint. If you already know it, we bootstrap on its origin (the most reliable choice). Takes precedence over `websiteDomain`; overridden by `bootstrapURL`. |
| `websiteDomain` | `string` | no | Shorthand alternative to `bootstrapURL` — just the domain to bootstrap on (e.g. `www.example.com`). Ignored if `bootstrapURL` or `pjsUrl` is set. |

> **API endpoints.** Kasada's challenge script is served on HTML pages, not
> on API hosts. When `websiteURL` is an API endpoint (a host like
> `api.…`/`gateway.…`, or a path containing `/graphql`, `/api/`, `/vN/`,
> or ending in `.json`), Capzy automatically navigates to a bootstrap page
> to arm the SDK, then mints `x-kpsdk-cd` against your endpoint. If the
> auto-derived host root doesn't serve the challenge, pass `bootstrapURL`
> (or `websiteDomain`) pointing at the brand's web page.

### `KasadaCaptchaCDTask` — browserless CD generator

Generates a fresh single-use `x-kpsdk-cd` from your own live session values — no
browser, no proxy, microseconds per call. The CD is a chained-SHA256 proof-of-work:
`seed = sha256(s, workTime, id, K)`, then a nonce search per subchallenge clears the
difficulty target, chained through the rounds. You supply the session values; we hold
the per-site challenge configuration (resolved from `site`).

| Field | Type | Required | Notes |
|-------|------|:--------:|-------|
| `type` | `string` | yes | `KasadaCaptchaCDTask` |
| `site` | `string` | yes | Site identifier — we resolve the per-site challenge configuration. Contact support if your site isn't supported yet. |
| `s` | `string` | yes | `platformInputs` — the per-request value from your live Kasada session (e.g. `tp-v2-input…`). It rotates frequently, so read it fresh from the session you're replaying against. Alias: `platformInputs`. |
| `ct` | `string` | yes | `x-kpsdk-ct` from the `/tl` response header (your session token) — echoed back for replay. |
| `st` | `string` | yes | `x-kpsdk-st` from the `/tl` response header — written into the cd's `st` field. |
| `fc` | `string` | no | `x-kpsdk-fc` from the `/mfc` response header — base64 `cryptoChallenge` config that sets the difficulty / subchallenge count when present. Omit to use the site default. |
| `workTime` | `integer` | no | Override the cd's `workTime` (ms). Defaults to now. |
| `id` | `string` | no | Override the 32-hex cd `id`. Defaults to a fresh random id. |

> **No proxy fields** — CD generation is pure computation and IP-independent.
> The CD is single-use and valid ~5 seconds from its `workTime`; generate it
> immediately before the request you need it for. Reuse the same `ct`/`st`/
> User-Agent across the session that minted them — the cd binds to that session.


### Proxy fields (only for `KasadaCaptchaTask`)

| Field | Type | Required | Notes |
|-------|------|:--------:|-------|
| `proxyType` | `string` | no | http | https | socks4 | socks5 |
| `proxyAddress` | `string` | no | IP or hostname of your proxy |
| `proxyPort` | `integer` | no | Port number of your proxy |
| `proxyLogin` | `string` | no | Optional — omit if your proxy doesn't require auth |
| `proxyPassword` | `string` | no | Optional — omit if your proxy doesn't require auth |


## Response

### `POST /createTask` success

```json
{
  "errorId": 0,
  "taskId":  "12345"
}
```

### `POST /getTaskResult` while processing

```json
{
  "errorId": 0,
  "status":  "processing"
}
```

### `POST /getTaskResult` when ready

```json
{
  "errorId":  0,
  "status":   "ready",
  "solution": { ... }
}
```

The `solution` object contains:

| Field | Type | Notes |
|-------|------|-------|
| `x-kpsdk-ct` | `string` | Client token (~30 min lifetime, reusable) |
| `x-kpsdk-cd` | `string` | Client data with proof-of-work (single-use per request) |
| `cookies` | `object` | KP_UIDz and KP_UIDz-ssn session cookies |
| `userAgent` | `string` | User-Agent used during solve — must reuse for subsequent requests |
| `expiresAt` | `number` | Unix timestamp when the CT expires |

### How to use the solution

Add `x-kpsdk-ct` and `x-kpsdk-cd` as HTTP headers, set the KP_UIDz cookies, and use the exact User-Agent. CT lasts ~30 minutes — re-solve only `cd` for each subsequent request.

### Error

```json
{
  "errorId":          1,
  "errorCode":        "ERROR_KEY_DOES_NOT_EXIST",
  "errorDescription": "Invalid API key"
}
```

`errorId` is `0` on success, `1` on any error. The `errorCode` is the
stable machine-readable identifier. Common codes:

- `ERROR_KEY_DOES_NOT_EXIST` — bad API key
- `ERROR_NO_BALANCE` — account balance below the cost of this task
- `ERROR_INVALID_PARAMS` — missing required field or malformed value
- `ERROR_MAX_TASKS_REACHED` — concurrent in-flight cap reached (default 30)
- `ERROR_RATE_LIMITED` — too many createTask calls per second
- `ERROR_TIMEOUT` — solve took longer than the cap (auto-refunded)
- `ERROR_CAPTCHA_UNSOLVABLE` — solver gave up (auto-refunded)

## Naming conventions

Field names are camelCase on the wire (`websiteURL`, `websiteKey`,
`proxyAddress`). Stick to that exactly when you build the JSON.
