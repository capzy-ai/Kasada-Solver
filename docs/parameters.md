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
| `websiteURL` | `string` | yes | The Kasada-protected URL you want tokens for. **Use the full canonical page URL, including `www` and a trailing slash** (e.g. `https://www.example.com/`); a bare apex domain often won't arm the Kasada challenge, so no tokens come back. Can be an HTML page **or** a JSON/GraphQL API endpoint (e.g. `https://api.example.com/graphql`). Accepted aliases: `pageURL`, `websiteUrl`. |
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

Generates a fresh single-use `x-kpsdk-cd` from your own live session values. No
browser, no proxy, microseconds per call. The CD is a chained-SHA256 proof-of-work:
`seed = sha256(s, workTime, id, k)`, then a nonce search per subchallenge clears the
difficulty target, chained through the rounds. You send your session values plus
your site's `k`; we run the proof and hand back the token.

| Field | Type | Required | Notes |
|-------|------|:--------:|-------|
| `type` | `string` | yes | `KasadaCaptchaCDTask` |
| `k` | `string` | yes | Your site's proof-of-work constant (64-char hex). Extract it once with [`get_k.py`](../examples/python/get_k.py), then reuse it. It is stable per site. See [where each value comes from](#where-each-value-comes-from). |
| `ct` | `string` | yes | `x-kpsdk-ct` from the `/tl` response header (your session token), echoed back for replay. |
| `st` | `string` | yes | `x-kpsdk-st` from the `/tl` response header, written into the cd's `st` field. |
| `fc` | `string` | no | `x-kpsdk-fc` from the `/mfc` response header. base64 `cryptoChallenge` config that sets the difficulty / subchallenge count when present. Omit to use the site default. |
| `s` | `string` | no | `platformInputs`. Defaults to the v2 base `tp-v2-input`, which validates on v2 sites. Only set it if your site uses a per-request suffix (`get_k.py` prints the `s` it observed). Alias: `platformInputs`. |
| `workTime` | `integer` | no | Override the cd's `workTime` (ms). Defaults to now. |
| `id` | `string` | no | Override the 32-hex cd `id`. Defaults to a fresh random id. |

> **No proxy fields.** CD generation is pure computation and IP-independent.
> The CD is single-use and valid ~5 seconds from its `workTime`; generate it
> immediately before the request you need it for. Reuse the same `ct`/`st`/
> User-Agent across the session that minted them. the cd binds to that session.

> **Most integrations don't need this task.** `KasadaCaptchaTask` /
> `…ProxyLess` already return a ready-to-use `x-kpsdk-cd` alongside `x-kpsdk-ct`
> in a single solve, with no `k` and no script. Reach for `KasadaCaptchaCDTask`
> only when you run your own long-lived Kasada session and want to mint many fresh
> CDs from one `k` without re-launching a browser each time.

#### Where each value comes from

**`ct` / `st` / `fc`** you read off your own session. From a real unblocked
session on the target (your browser's DevTools → Network, or the HTTP client that
holds the session):

1. Tick **Preserve log**, filter by `tl`, open the `POST …/<uuid>/<uuid>/tl`
   request. Its **Response Headers** give you:
   - `x-kpsdk-ct` → **`ct`**
   - `x-kpsdk-st` → **`st`**
2. Filter by `mfc`; if the site makes that request, its `x-kpsdk-fc` response
   header → **`fc`** (omit `fc` when there's no `/mfc` request; many sites have none).

**`k`** is your site's proof-of-work constant. It is not on the page, not a
header, and not a field of the `x-kpsdk-cd` body, so we extract it for you: submit
a **`KasadaGetKTask`** with your `websiteURL`. We run a real browser on your
target, watch Kasada mint a token, read `k` out of the proof-of-work input, and
**validate it against that live token** before returning it. This task is **free**
(cost 0), but it goes through `createTask` with your API key, so the run is tracked
on your account.

```bash
# Get your k (free, tracked on your key):
curl -s https://api.capzy.ai/createTask -H 'Content-Type: application/json' -d '{
  "clientKey": "capzy_xxxxxxxxxxxxxxxxxxxxxxxx",
  "task": { "type": "KasadaGetKTaskProxyLess", "websiteURL": "https://www.your-target.com/" }
}'
# poll getTaskResult -> { "solution": { "k": "<64-hex constant>", "s": "tp-v2-input", "validated": true } }
```

Run it once, save the `k`, and reuse it on every CD call. It is stable per site.
There's also a point-and-click version on the
[product page](https://capzy.ai/solvers/kasada-cd) (Get your values tab), and a
self-host script [`get_k.py`](../examples/python/get_k.py) if you'd rather run it
locally.

#### Worked example

```bash
curl -s https://api.capzy.ai/createTask -H 'Content-Type: application/json' -d '{
  "clientKey": "capzy_xxxxxxxxxxxxxxxxxxxxxxxx",
  "task": {
    "type": "KasadaCaptchaCDTask",
    "k":    "<your site k, from get_k.py>",
    "ct":   "0aXY...    (x-kpsdk-ct from the /tl response)",
    "st":   "1721800000 (x-kpsdk-st from the /tl response)",
    "fc":   "eyJ...      (x-kpsdk-fc from the /mfc response, optional)"
  }
}'
```

The `solution` returns a fresh `x-kpsdk-cd` (plus your `ct`/`st` echoed back).
Attach `x-kpsdk-cd` + `x-kpsdk-ct` as request headers within ~5 seconds, on the
same session/User-Agent you captured the inputs from.


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
