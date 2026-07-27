"""
Get your site's Kasada `k` (the proof-of-work constant) for KasadaCaptchaCDTask.

`k` is a per-site 64-hex value baked into the site's Kasada script. It is stable
per site, so you extract it ONCE, save it, and reuse it on every CD call. This
script drives a real browser on your target, watches the Kasada SDK compute a
token, reads the `k` out of the proof-of-work input, and VALIDATES it by
reproducing a real token the browser minted. It only prints a `k` it proved.

    pip install playwright
    playwright install chromium
    python get_k.py --url https://www.your-target.com/

    # through your own proxy (recommended if a plain run gets blocked):
    python get_k.py --url https://www.your-target.com/ \
        --proxy http://user:pass@host:port

Output: the 64-hex `k`. Then call the API with it:

    task = {"type": "KasadaCaptchaCDTask", "k": "<that value>",
            "ct": ct, "st": st, "fc": fc}

Nothing here talks to Capzy; it inspects only your target site. Save the `k`
somewhere (env var, your DB, a config file) and reuse it.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import sys
import urllib.parse

from playwright.async_api import async_playwright

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36")

# The Kasada CD proof-of-work is chained SHA-256 over `s, workTime, id, k`.
# We only need it to VALIDATE a captured k against a real token.
_TARGET_NUM = 0x10000000000000  # 2^52
_DEFAULT_TARGET = 4.0


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _reproduce_answers(s: str, k: str, work_time: int, cd_id: str,
                       subchallenge_count: int = 2, target: float = _DEFAULT_TARGET) -> list[int]:
    seed = _sha(f"{s}, {work_time}, {cd_id}, {k}")
    answers: list[int] = []
    for _ in range(max(1, subchallenge_count)):
        n = 1
        while n < 5_000_000:
            cand = _sha(f"{n}, {seed}")
            if _TARGET_NUM / (int(cand[:13], 16) + 1) >= target:
                answers.append(n)
                seed = cand
                break
            n += 1
        else:
            answers.append(-1)
    return answers


# Injected into EVERY JS realm (main window + each worker/iframe). It hooks the
# string/encoding entrypoints the Kasada PoW uses and reports any hashed string
# back through the __capzy_send binding. The 4-field preimage `s, wt, id, k` is
# what we're after; `k` is its trailing 64-hex group.
SEED_HOOK = r"""
(function(){
  try {
    var g = (typeof globalThis!=='undefined')?globalThis:this;
    var send = function(t){ try{ if(typeof g.__capzy_send==='function') g.__capzy_send(t); }catch(e){} };
    if (!g.__capzy_caps) g.__capzy_caps = [];
    var seen = Object.create(null);
    var look = function(s){
      try {
        if (typeof s!=='string') return;
        if (s.length<8 || s.length>600) return;
        if (s.indexOf(', ')<0 && !/^[0-9a-f]{64}$/.test(s)) return;
        if (seen[s]) return; seen[s]=1;
        g.__capzy_caps.push(s); send('__S__'+s);
      } catch(e){}
    };
    var install = function(W){
      try {
        if (!W || W.__capzy_hooked) return; W.__capzy_hooked = 1;
        var SP = W.String && W.String.prototype;
        if (SP && SP.charCodeAt){ var cc = SP.charCodeAt;
          Object.defineProperty(SP,'charCodeAt',{configurable:true,writable:true,
            value:function(i){ try{ if(i===0) look(''+this);}catch(e){} return cc.call(this,i); }}); }
        var TE = W.TextEncoder && W.TextEncoder.prototype;
        if (TE && TE.encode){ var te=TE.encode; TE.encode=function(s){ try{look(s);}catch(e){} return te.call(this,s); }; }
        if (TE && TE.encodeInto){ var tei=TE.encodeInto; TE.encodeInto=function(s,b){ try{look(s);}catch(e){} return tei.call(this,s,b); }; }
      } catch(e){}
    };
    install(g);
    try {
      if (g.document && g.Node && g.Node.prototype){
        var hook = function(n){ try{ if(n && n.tagName==='IFRAME'){ install(n.contentWindow);
          n.addEventListener && n.addEventListener('load', function(){ try{install(n.contentWindow);}catch(e){} }); } }catch(e){} };
        var ac=g.Node.prototype.appendChild; if(ac){ g.Node.prototype.appendChild=function(x){ var r=ac.call(this,x); try{hook(x);}catch(e){} return r; }; }
        var ib=g.Node.prototype.insertBefore; if(ib){ g.Node.prototype.insertBefore=function(x,y){ var r=ib.call(this,x,y); try{hook(x);}catch(e){} return r; }; }
      }
    } catch(e){}
  } catch(e){}
})();
"""

# Records every x-kpsdk-cd the SDK stamps, with its ct/st/fc context. These real
# tokens are the oracle we validate the captured `k` against.
CD_HOOK = r"""
(() => {
  if (window.__cd_log) return; window.__cd_log = []; window.__cd_ctx = {ct:'',st:'',fc:''};
  const grab=(k,v)=>{ if(v) window.__cd_ctx[k]=v; };
  const rec=(h)=>{ try{ let cd=''; for(const k of Object.keys(h||{})){ const lk=k.toLowerCase(),v=h[k];
      if(lk==='x-kpsdk-cd')cd=v; if(lk==='x-kpsdk-ct')grab('ct',v); if(lk==='x-kpsdk-st')grab('st',v); if(lk==='x-kpsdk-fc')grab('fc',v); }
    if(cd) window.__cd_log.push({cd,ct:window.__cd_ctx.ct,st:window.__cd_ctx.st,fc:window.__cd_ctx.fc});}catch(e){} };
  const of=window.fetch; window.fetch=function(input,init){ try{ const hd=(init&&init.headers)||(input&&input.headers);
      if(hd){ const h=hd instanceof Headers?Object.fromEntries(hd.entries()):hd; rec(h);} }catch(e){}
    return of.apply(this,arguments).then(r=>{ try{ grab('ct',r.headers.get('x-kpsdk-ct')); grab('st',r.headers.get('x-kpsdk-st')); grab('fc',r.headers.get('x-kpsdk-fc')); }catch(e){} return r; }); };
  const os=XMLHttpRequest.prototype.setRequestHeader;
  XMLHttpRequest.prototype.setRequestHeader=function(n,v){ try{ if((n||'').toLowerCase().startsWith('x-kpsdk-')) rec({[n]:v}); }catch(e){} return os.apply(this,arguments); };
})();
"""


def parse_cd(raw: str) -> dict | None:
    for attempt in (raw, urllib.parse.unquote(raw)):
        try:
            obj = json.loads(attempt)
            if isinstance(obj, dict) and "answers" in obj and "workTime" in obj:
                return obj
        except Exception:
            pass
    return None


def find_k(preimages: list[str], real_cds: list[dict]) -> tuple[str, str] | None:
    """Return (k, s) if a captured preimage's (workTime,id) matches a real token
    AND reproduces its answers. That match proves the k."""
    for cd in real_cds:
        wt, cid, ans = cd.get("workTime"), cd.get("id"), cd.get("answers")
        if not (isinstance(wt, int) and isinstance(cid, str) and isinstance(ans, list)):
            continue
        pat = re.compile(r"^(.+?), %d, %s, ([0-9a-f]{64})\b" % (wt, re.escape(cid)))
        for p in preimages:
            m = pat.match(p)
            if m and _reproduce_answers(m.group(1), m.group(2), wt, cid) == ans:
                return m.group(2), m.group(1)
    return None


async def harvest(url: str, proxy: str | None, n_probes: int) -> int:
    host = urllib.parse.urlparse(url).netloc
    caps: list[str] = []
    workers: set[str] = set()

    launch: dict = {"headless": True}
    if proxy:
        launch["proxy"] = {"server": proxy}

    pw = await async_playwright().start()
    b = await pw.chromium.launch(**launch)
    ctx = await b.new_context(user_agent=UA, viewport={"width": 1280, "height": 850})
    await ctx.add_init_script(CD_HOOK)
    await ctx.add_init_script(SEED_HOOK)
    page = await ctx.new_page()
    cdp = await ctx.new_cdp_session(page)

    _mid = [1000]
    async def to_target(sid, method, params=None):
        _mid[0] += 1
        try:
            await cdp.send("Target.sendMessageToTarget", {
                "sessionId": sid,
                "message": json.dumps({"id": _mid[0], "method": method, "params": params or {}}),
            })
        except Exception:
            pass

    def note(v):
        if isinstance(v, str) and v.startswith("__S__"):
            caps.append(v[len("__S__"):])

    async def setup_worker(ti, sid):
        if not sid or sid in workers:
            return
        workers.add(sid)
        await to_target(sid, "Target.setAutoAttach",
                        {"autoAttach": True, "waitForDebuggerOnStart": True, "flatten": False})
        await to_target(sid, "Runtime.addBinding", {"name": "__capzy_send"})
        await to_target(sid, "Runtime.enable")

    def on_recv(p):
        try:
            inner = json.loads(p.get("message", "{}"))
            m = inner.get("method")
            if m == "Runtime.bindingCalled" and inner.get("params", {}).get("name") == "__capzy_send":
                note(inner["params"].get("payload", ""))
            elif m == "Runtime.executionContextCreated":
                cid = inner["params"]["context"]["id"]; sid = p.get("sessionId")
                if sid:
                    async def _inj(sid=sid, cid=cid):
                        await to_target(sid, "Runtime.evaluate", {"expression": SEED_HOOK, "contextId": cid, "silent": True})
                        await to_target(sid, "Runtime.runIfWaitingForDebugger")
                    asyncio.create_task(_inj())
            elif m == "Target.attachedToTarget":
                pr = inner.get("params", {})
                asyncio.create_task(setup_worker(pr.get("targetInfo", {}), pr.get("sessionId")))
        except Exception:
            pass

    async def inject_main(ctx_id):
        try:
            await cdp.send("Runtime.evaluate", {"expression": SEED_HOOK, "contextId": ctx_id, "silent": True})
        except Exception:
            pass
    cdp.on("Runtime.executionContextCreated",
           lambda p: asyncio.create_task(inject_main(p["context"]["id"])))
    cdp.on("Runtime.bindingCalled",
           lambda p: note(p.get("payload", "")) if p.get("name") == "__capzy_send" else None)
    cdp.on("Target.attachedToTarget",
           lambda p: asyncio.create_task(setup_worker(p.get("targetInfo", {}), p.get("sessionId"))))
    cdp.on("Target.receivedMessageFromTarget", on_recv)
    await cdp.send("Runtime.enable")
    await cdp.send("Runtime.addBinding", {"name": "__capzy_send"})
    await cdp.send("Page.enable")
    try:
        await cdp.send("Page.addScriptToEvaluateOnNewDocument", {"source": SEED_HOOK, "runImmediately": True})
    except Exception:
        await cdp.send("Page.addScriptToEvaluateOnNewDocument", {"source": SEED_HOOK})
    await cdp.send("Target.setAutoAttach",
                   {"autoAttach": True, "waitForDebuggerOnStart": True, "flatten": False})

    print(f"[.] loading {host} ...", flush=True)
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
    except Exception as e:
        print(f"    nav warning: {str(e)[:80]}", flush=True)
    for _ in range(40):
        await asyncio.sleep(0.5)
        try:
            if await page.evaluate("()=>!!(window.KPSDK&&window.KPSDK.isReady&&window.KPSDK.isReady())"):
                break
        except Exception:
            pass
    try:
        await page.evaluate("""()=>{try{if(window.KPSDK&&typeof window.KPSDK.configure==='function')
            window.KPSDK.configure([{domain:location.hostname,method:'GET',path:'/',protocol:'https:'}]);}catch(e){}}""")
    except Exception:
        pass
    print(f"[.] triggering {n_probes} token(s) ...", flush=True)
    for i in range(n_probes):
        try:
            await page.evaluate("(i)=>fetch(location.origin+'/?_c='+Date.now()+'_'+i,{credentials:'include',cache:'no-store'}).catch(()=>{})", i)
        except Exception:
            pass
        await asyncio.sleep(0.4)
    await asyncio.sleep(1.5)

    try:
        main_caps = await page.evaluate("()=>JSON.stringify((window.__capzy_caps)||[])")
        for s in json.loads(main_caps or "[]"):
            if isinstance(s, str):
                caps.append(s)
        cd_log = await page.evaluate("()=>window.__cd_log||[]")
    except Exception:
        cd_log = []
    await b.close()
    await pw.stop()

    uniq = list(dict.fromkeys(caps))
    real_cds = [c for c in (parse_cd(e.get("cd", "")) for e in cd_log) if c]
    print(f"[.] captured {len(uniq)} preimage(s), {len(real_cds)} live token(s)", flush=True)

    if not real_cds:
        print("\n[x] The site did not mint a token on this run. It likely flagged the "
              "connection. Re-run through a residential/clean IP with --proxy.", file=sys.stderr)
        return 2
    found = find_k(uniq, real_cds)
    if not found:
        print("\n[x] Could not confirm k this run (no captured proof matched a live token). "
              "Re-run, optionally with --proxy and a higher --n.", file=sys.stderr)
        return 3

    k, s = found
    print("\n[OK] Validated against a live token.")
    print(f"     site : {host}")
    print(f"     s    : {s}")
    print(f"\nk = {k}\n")
    print("Save this k and pass it to KasadaCaptchaCDTask as \"k\". It is stable per site.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Extract your site's Kasada k for KasadaCaptchaCDTask.")
    ap.add_argument("--url", required=True,
                    help="A Kasada-protected page on your target site. Use the canonical URL "
                         "with www and a trailing slash, e.g. https://www.example.com/ (a bare "
                         "apex domain may not arm the SDK).")
    ap.add_argument("--proxy", default="", help="Optional proxy, e.g. http://user:pass@host:port")
    ap.add_argument("--n", type=int, default=12, help="How many tokens to trigger (default 12).")
    args = ap.parse_args()
    return asyncio.run(harvest(args.url, args.proxy or None, args.n))


if __name__ == "__main__":
    raise SystemExit(main())
