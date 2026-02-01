#!/usr/bin/env python3
import base64
import json
import os
import sys
import time
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler

RPC_HOST = os.environ.get("MFLEX_RPC_HOST", "retro-mike-mflex-node_node_1")
RPC_PORT = int(os.environ.get("MFLEX_RPC_PORT", "9010"))
RPC_USER = os.environ.get("MFLEX_RPC_USER", "pooluser")
RPC_PASS = os.environ.get("MFLEX_RPC_PASS", "poolpassword")
WALLET_NAME = os.environ.get("MFLEX_WALLET", "pool")
ADDR_TYPE = os.environ.get("MFLEX_ADDR_TYPE", "legacy")  # "legacy" for base58

POOL_ID = os.environ.get("POOL_ID", "mflex")
CONFIG_PATH = os.environ.get("MININGCORE_CONFIG", "/mc/config.json")

LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = int(os.environ.get("PORT", "8080"))

INDEX_HTML = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>MFLEX Miningcore Helper</title>
  <style>
    body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin: 24px; max-width: 900px; }}
    button {{ padding: 10px 14px; font-size: 16px; cursor: pointer; }}
    pre {{ background: #111; color: #eee; padding: 12px; border-radius: 8px; overflow: auto; }}
    .row {{ display:flex; gap:12px; flex-wrap:wrap; margin-bottom:12px; }}
    .muted {{ opacity: 0.75; }}
  </style>
</head>
<body>
  <h2>MFLEX Miningcore Helper</h2>
  <p class="muted">
    This tool will create/load the MFLEX wallet <b>{WALLET_NAME}</b>, generate a <b>{ADDR_TYPE}</b> address,
    and write it into Miningcore config (<code>{CONFIG_PATH}</code>) for pool id <b>{POOL_ID}</b>.
  </p>

  <div class="row">
    <button onclick="run()">Generate address + write config</button>
    <button onclick="status()">Show current config status</button>
  </div>

  <pre id="out">Ready.</pre>

<script>
async function run() {{
  const out = document.getElementById('out');
  out.textContent = "Working...";
  try {{
    const r = await fetch('/run', {{ method:'POST' }});
    const t = await r.text();
    out.textContent = t;
  }} catch(e) {{
    out.textContent = String(e);
  }}
}}
async function status() {{
  const out = document.getElementById('out');
  out.textContent = "Loading...";
  try {{
    const r = await fetch('/status');
    const t = await r.text();
    out.textContent = t;
  }} catch(e) {{
    out.textContent = String(e);
  }}
}}
</script>
</body>
</html>
"""

def rpc_call(method, params=None, wallet=None, timeout=10):
    if params is None:
        params = []
    url = f"http://{RPC_HOST}:{RPC_PORT}/"
    if wallet:
        url = url + f"wallet/{wallet}"
    payload = json.dumps({
        "jsonrpc": "1.0",
        "id": "mflex-helper",
        "method": method,
        "params": params
    }).encode("utf-8")

    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "text/plain;")
    auth = base64.b64encode(f"{RPC_USER}:{RPC_PASS}".encode("utf-8")).decode("ascii")
    req.add_header("Authorization", "Basic " + auth)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        try:
            raw = e.read().decode("utf-8", errors="replace")
        except Exception:
            raw = str(e)
        return {"result": None, "error": {"code": -1, "message": f"HTTPError {e.code}: {raw}"}, "id": "mflex-helper"}
    except Exception as e:
        return {"result": None, "error": {"code": -1, "message": str(e)}, "id": "mflex-helper"}

def ensure_wallet_loaded():
    # createwallet may fail if it already exists; ignore
    rpc_call("createwallet", [WALLET_NAME])
    # loadwallet may fail if already loaded; ignore
    rpc_call("loadwallet", [WALLET_NAME])

def get_new_legacy_address():
    r = rpc_call("getnewaddress", ["", ADDR_TYPE], wallet=WALLET_NAME)
    if r.get("error"):
        raise RuntimeError(r["error"].get("message") or str(r["error"]))
    addr = (r.get("result") or "").strip()
    if not addr:
        raise RuntimeError("getnewaddress returned empty result")
    return addr

def patch_miningcore_config(new_address: str):
    if not os.path.exists(CONFIG_PATH):
        raise RuntimeError(f"Miningcore config not found: {CONFIG_PATH}")
    if os.path.isdir(CONFIG_PATH):
        raise RuntimeError(f"Miningcore config is a directory (must be a file): {CONFIG_PATH}")

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception as e:
        raise RuntimeError(f"Failed to parse config.json: {e}")

    pools = cfg.get("pools") or []
    if not isinstance(pools, list):
        raise RuntimeError("config.json: 'pools' is not a list")

    target = None
    for p in pools:
        if isinstance(p, dict) and p.get("id") == POOL_ID:
            target = p
            break

    if target is None:
        raise RuntimeError(f"Pool id '{POOL_ID}' not found in config.json")

    old_address = target.get("address")
    target["address"] = new_address

    # If rewardRecipients uses the old pool address, update those too
    rrs = target.get("rewardRecipients")
    if isinstance(rrs, list) and old_address:
        for rr in rrs:
            if isinstance(rr, dict) and rr.get("address") == old_address:
                rr["address"] = new_address

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")

    return old_address

def get_current_config_address():
    if not os.path.exists(CONFIG_PATH) or os.path.isdir(CONFIG_PATH):
        return None
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        return None
    pools = cfg.get("pools") or []
    for p in pools:
        if isinstance(p, dict) and p.get("id") == POOL_ID:
            return p.get("address")
    return None

class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, content_type="text/plain; charset=utf-8"):
        b = body.encode("utf-8", errors="replace")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, fmt, *args):
        # quieter logs
        sys.stdout.write("%s - %s\n" % (self.address_string(), fmt % args))
        sys.stdout.flush()

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/?"):
            return self._send(200, INDEX_HTML, "text/html; charset=utf-8")

        if self.path == "/status":
            status = {
                "rpc": f"http://{RPC_HOST}:{RPC_PORT}",
                "wallet": WALLET_NAME,
                "pool_id": POOL_ID,
                "config_path": CONFIG_PATH,
                "config_pool_address": get_current_config_address()
            }
            return self._send(200, json.dumps(status, indent=2) + "\n", "application/json; charset=utf-8")

        return self._send(404, "not found\n")

    def do_POST(self):
        if self.path != "/run":
            return self._send(404, "not found\n")

        started = time.time()
        try:
            ensure_wallet_loaded()
            addr = get_new_legacy_address()
            old = patch_miningcore_config(addr)
            out = {
                "ok": True,
                "new_address": addr,
                "old_address": old,
                "pool_id": POOL_ID,
                "config_path": CONFIG_PATH,
                "seconds": round(time.time() - started, 3)
            }
            return self._send(200, json.dumps(out, indent=2) + "\n", "application/json; charset=utf-8")
        except Exception as e:
            out = {
                "ok": False,
                "error": str(e),
                "pool_id": POOL_ID,
                "config_path": CONFIG_PATH
            }
            return self._send(500, json.dumps(out, indent=2) + "\n", "application/json; charset=utf-8")

def main():
    print(f"[mflex-helper] listening on http://{LISTEN_HOST}:{LISTEN_PORT}")
    httpd = HTTPServer((LISTEN_HOST, LISTEN_PORT), Handler)
    httpd.serve_forever()

if __name__ == "__main__":
    main()
