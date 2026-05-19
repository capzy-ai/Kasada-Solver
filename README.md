<div align="center">

<img src="https://capzy.ai/capzy-logo.svg" alt="Capzy" width="220" />

# Kasada Bot Defense Solver

**Bypass Kasada. Returns x-kpsdk-ct + x-kpsdk-cd + cookies in ~1.6s.**

[![Solve cost](https://img.shields.io/badge/from-%240.001%20%2F%20solve-%23ff5d2a)](https://capzy.ai/pricing)
[![Speed](https://img.shields.io/badge/avg%20solve-~1.6%20seconds-%2322c55e)](https://capzy.ai/products/kasada)
[![Uptime](https://img.shields.io/badge/uptime-99.9%25-%2322c55e)](https://capzy.ai/status)
[![License: MIT](https://img.shields.io/badge/license-MIT-%23ff5d2a)](LICENSE)

[Live Demo](https://capzy.ai/products/kasada/demo) ·
[Get Free $0.10 Credit](https://capzy.ai/auth/register) ·
[Dashboard](https://capzy.ai/dashboard) ·
[Full Docs](https://capzy.ai/docs) ·
[Pricing](https://capzy.ai/pricing)

</div>

---

## What this repo is

Copy-pasteable examples for solving **Kasada Bot Defense** through the
[Capzy](https://capzy.ai) HTTP API — no SDK required. Pure curl, Python,
and Node.js using the raw API. Easy to read, easy to port, easy to audit.

## What is Kasada Bot Defense?

Kasada is a bot defense platform that uses a custom JavaScript VM (ips.js) to fingerprint browsers and generate proof-of-work tokens. Two tokens are used: `x-kpsdk-ct` (client token, ~30 min lifetime) and `x-kpsdk-cd` (single-use proof of work). Capzy returns both plus the KP_UIDz session cookies.

## Why Capzy

- **From $0.001 per solve.** Flat pricing — no tiers, no retainer, no monthly minimum.
- **~1.6 seconds average solve.** Production-grade speed.
- **Drop-in compatible.** `createTask` / `getTaskResult` protocol. If your code already speaks the standard solver shape, swap the host to `https://api.capzy.ai`.
- **$0.10 in real credits on sign-up.** No card. 100 free test solves.

## Pricing

| Task type | When to use | Cost / solve |
|-----------|-------------|-------------:|
| `KasadaCaptchaTaskProxyLess`             | Proxyless (Capzy supplies the IP) | **$0.001**   |
| `KasadaCaptchaTask`                       | You supply the proxy              | **$0.001**   |

For consistency across the target site, use the proxy variant with the
**same proxy your session is already running through** — the solver
mints the token from that IP, so when you submit it back through the
same proxy everything looks consistent.

## 60-second quickstart

```bash
# 1. Sign up — gets you $0.10 in free credits (100 solves)
open https://capzy.ai/auth/register

# 2. Copy your API key from the dashboard
#    https://capzy.ai/dashboard/api-keys

# 3. Run any example
export CAPZY_KEY="capzy_..."
bash examples/curl/basic.sh
```

Minimal Python:

```python
import requests, time

KEY = "capzy_xxxxxxxxxxxxxxxxxxxxxxxx"

# 1) Create the task
created = requests.post("https://api.capzy.ai/createTask", json={
    "clientKey": KEY,
    "task": {
        "type": "KasadaCaptchaTaskProxyLess",
        "websiteURL": "https://example.com/"
    },
}).json()
task_id = created["taskId"]

# 2) Poll until ready
while True:
    result = requests.post("https://api.capzy.ai/getTaskResult", json={
        "clientKey": KEY, "taskId": task_id,
    }).json()
    if result["status"] == "ready":
        break
    time.sleep(2)

print(result["solution"])
```

That's the whole protocol. The rest of this repo is just that, in every
language we could think of.

## Pick your language

| Language        | Example                                       |
|-----------------|-----------------------------------------------|
| **curl / bash** | [`examples/curl/basic.sh`](examples/curl/basic.sh)    |
| **Python**      | [`examples/python/basic.py`](examples/python/basic.py) |
| **Node.js**     | [`examples/nodejs/basic.js`](examples/nodejs/basic.js) |

See [`examples/README.md`](examples/README.md) for setup details.

## Request envelope

```json
{
  "clientKey": "capzy_xxxxxxxxxxxxxxxxxxxxxxxx",
  "task": {
    "type": "KasadaCaptchaTaskProxyLess",
    "websiteURL": "https://example.com/"
  }
}
```

| Field | Type | Required | Notes |
|-------|------|:--------:|-------|
| `type` | `string` | yes | KasadaCaptchaTaskProxyLess or KasadaCaptchaTask |
| `websiteURL` | `string` | yes | Any URL on the Kasada-protected domain |
| `proxyType` | `string` | no  | http | https | socks4 | socks5 (only for `KasadaCaptchaTask`) |
| `proxyAddress` | `string` | no  | IP or hostname of your proxy (only for `KasadaCaptchaTask`) |
| `proxyPort` | `integer` | no  | Port number of your proxy (only for `KasadaCaptchaTask`) |
| `proxyLogin` | `string` | no  | Optional — omit if your proxy doesn't require auth (only for `KasadaCaptchaTask`) |
| `proxyPassword` | `string` | no  | Optional — omit if your proxy doesn't require auth (only for `KasadaCaptchaTask`) |

Full reference in [`docs/parameters.md`](docs/parameters.md).

## Response shape

When the task is ready (`status: "ready"`), `solution` contains:

| Field | Type | Notes |
|-------|------|-------|
| `x-kpsdk-ct` | `string` | Client token (~30 min lifetime, reusable) |
| `x-kpsdk-cd` | `string` | Client data with proof-of-work (single-use per request) |
| `cookies` | `object` | KP_UIDz and KP_UIDz-ssn session cookies |
| `userAgent` | `string` | User-Agent used during solve — must reuse for subsequent requests |
| `expiresAt` | `number` | Unix timestamp when the CT expires |

### How to use the result

Add `x-kpsdk-ct` and `x-kpsdk-cd` as HTTP headers, set the KP_UIDz cookies, and use the exact User-Agent. CT lasts ~30 minutes — re-solve only `cd` for each subsequent request.

## Features

- ~1.6 second solve time
- Returns the full token chain (ct + cd + cookies) in one request
- CT reusable for ~30 minutes — only `cd` is single-use

## FAQ

**x-kpsdk-cd is single-use. How do I get more?** Create a new task with the same URL to mint a fresh `cd`. The CT (client token) stays valid for ~30 minutes; you only need a new task per request, not a full new session.

## What you'll need

- A Capzy API key — [sign up](https://capzy.ai/auth/register) (free, $0.10 credit).
- Network access to `https://api.capzy.ai`.

## Other captcha types

Capzy solves 25+ captcha types. Full catalog at
[capzy.ai/pricing](https://capzy.ai/pricing). Each type has its own
solver repo on [github.com/capzy-ai](https://github.com/capzy-ai).

## License

[MIT](LICENSE).

---

<div align="center">

**[Sign up for free credits →](https://capzy.ai/auth/register)**

Built by [Capzy](https://capzy.ai). Issues + PRs welcome.

</div>
