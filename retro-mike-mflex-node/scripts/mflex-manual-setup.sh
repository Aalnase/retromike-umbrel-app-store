#!/usr/bin/env bash
# Run on Umbrel host (recommended: sudo)
# Creates/loads wallet "pool" and registers MFLEX pool in Miningcore.

RPC="http://127.0.0.1:9010"
USER="pooluser"
PASS="poolpassword"
WALLET="pool"
PM="/home/umbrel/umbrel/app-data/retro-mike-miningcore/scripts/pool-manager.sh"

echo "== wait for MFLEX RPC on $RPC =="
ok=""
for i in $(seq 1 120); do
  resp="$(curl -s --max-time 2 --user "$USER:$PASS" -H 'content-type: text/plain;' \
    --data-binary '{"jsonrpc":"1.0","id":"t","method":"getblockchaininfo","params":[]}' \
    "$RPC/" 2>/dev/null || true)"
  echo "$resp" | grep -q '"result"' && ok="yes" && break
  sleep 1
done

if [ -z "$ok" ]; then
  echo "ERROR: RPC not reachable on $RPC"
  exit 1
fi

echo "== ensure wallet '$WALLET' exists/loaded =="
curl -s --max-time 10 --user "$USER:$PASS" -H 'content-type: text/plain;' \
  --data-binary "{\"jsonrpc\":\"1.0\",\"id\":\"cw\",\"method\":\"createwallet\",\"params\":[\"$WALLET\"]}" \
  "$RPC/" >/dev/null 2>&1 || true

curl -s --max-time 10 --user "$USER:$PASS" -H 'content-type: text/plain;' \
  --data-binary "{\"jsonrpc\":\"1.0\",\"id\":\"lw\",\"method\":\"loadwallet\",\"params\":[\"$WALLET\"]}" \
  "$RPC/" >/dev/null 2>&1 || true

echo "== quick address sanity check (legacy) =="
addr="$(curl -s --max-time 10 --user "$USER:$PASS" -H 'content-type: text/plain;' \
  --data-binary '{"jsonrpc":"1.0","id":"na","method":"getnewaddress","params":["","legacy"]}' \
  "$RPC/wallet/$WALLET" \
  | python3 - <<'PY'
import sys, json
try:
    d=json.load(sys.stdin)
    print((d.get("result") or "").strip())
except Exception:
    print("")
PY
)"
if [ -z "$addr" ]; then
  echo "ERROR: getnewaddress failed (wallet not ready?)"
  exit 1
fi
echo "pool address (legacy) => $addr"

if [ ! -x "$PM" ]; then
  echo "ERROR: pool-manager not found at: $PM"
  exit 1
fi

echo "== register MFLEX pool in Miningcore =="
"$PM" register-bitcoin \
  --pool-id mflex \
  --coin multiflex \
  --app-id retro-mike-mflex-node \
  --rpc-port 9010 \
  --zmq-port 7010 \
  --stratum-port 6010 \
  --daemon-host retro-mike-mflex-node_node_1 \
  --rpc-wallet "$WALLET" \
  --getnewaddress-params '["","legacy"]' \
  --mflex-enabled

echo "== restart Miningcore =="
docker restart retro-mike-miningcore_server_1 >/dev/null 2>&1 || true

echo "DONE."
echo "  pools.d:  /home/umbrel/.miningcore/pools.d/mflex.json"
echo "  config:   /home/umbrel/.miningcore/config.json"
