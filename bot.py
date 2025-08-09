import os
import requests
from fastapi import FastAPI, Request
import uvicorn

app = FastAPI()

# --- ENV ---
WH_WHALE = os.getenv("WH_WHALE")          # webhook pro #whale-alerts
WH_WATCH = os.getenv("WH_WATCH")          # webhook pro #watchlist-alerts
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK", WH_WHALE)  # fallback: když nemáš DISCORD_WEBHOOK, použijeme WH_WHALE
THRESH_SOL = float(os.getenv("THRESH_SOL", "500"))

# --- watchlist ---
WATCHLIST = set()
if os.path.exists("watchlist.txt"):
    with open("watchlist.txt", "r", encoding="utf-8") as f:
        WATCHLIST = {x.strip() for x in f if x.strip()}

# --- helpers ---
def send_to_discord(message: str, webhook: str = None):
    url = webhook or DISCORD_WEBHOOK
    if not url:
        print("⚠️ Žádný Discord webhook (WH_WHALE/ DISCORD_WEBHOOK) není nastaven.")
        return
    try:
        r = requests.post(url, json={"content": message}, timeout=10)
        if r.status_code >= 300:
            print(f"❌ Discord webhook error {r.status_code}: {r.text}")
    except Exception as e:
        print(f"❌ Chyba při odesílání do Discordu: {e}")

def get_number(x, *keys, default=0):
    """Bezpečně vytáhne číslo z nested dictu i z plain int; vrací float."""
    if keys:
        for k in keys:
            if isinstance(x, dict):
                x = x.get(k)
            else:
                x = None
                break
    # teď x může být dict/int/float/None
    if isinstance(x, dict):
        # typicky {"amount": <int>} nebo {"token": <int>}
        for cand in ("amount", "token", "usd", "lamports"):
            if cand in x and isinstance(x[cand], (int, float)):
                return float(x[cand])
        return float(default)
    if isinstance(x, (int, float)):
        return float(x)
    return float(default)

def parse_and_alert(tx: dict):
    """
    Očekává Helius Enhanced webhook objekt jedné transakce:
      tx["type"] == "SWAP"
      tx["events"]["swap"] {...}
    """
    tx_type = (tx.get("type") or "").upper()
    if tx_type != "SWAP":
        return  # ignorujeme ostatní

    swap = (tx.get("events") or {}).get("swap") or {}
    # SOL utracené za nákup (lamports → SOL)
    lamports_in = get_number(swap, "nativeInput", default=0.0)
    lamports_out = get_number(swap, "nativeOutput", default=0.0)
    lamports = lamports_in if lamports_in > 0 else abs(lamports_out)
    sol_spent = lamports / 1_000_000_000.0

    if sol_spent <= 0:
        return

    buyer = (tx.get("accountData") or [{}])[0].get("account", {}).get("pubkey", None)
    token_mint = (swap.get("tokenOutput") or {}).get("mint") or (swap.get("tokenInput") or {}).get("mint") or "UNKNOWN"
    sig = tx.get("signature", "N/A")

    # kanál
    is_watch = buyer in WATCHLIST if buyer else False
    is_whale = sol_spent >= THRESH_SOL

    if not (is_watch or is_whale):
        return  # pod prahem a není ve watchlistu

    # zpráva
    dex_url = f"https://dexscreener.com/solana/{token_mint}" if token_mint != "UNKNOWN" else "https://dexscreener.com/solana"
    solscan_url = f"https://solscan.io/tx/{sig}"
    msg = (
        f"🐋 **Whale SWAP**\n"
        f"**BUY:** {sol_spent:.2f} SOL → `{token_mint}`\n"
        f"🔗 **Tx:** {solscan_url}\n"
        f"🔥 **DexScreener:** {dex_url}"
    )

    if is_watch and WH_WATCH:
        send_to_discord(msg, WH_WATCH)
    if is_whale and WH_WHALE:
        send_to_discord(msg, WH_WHALE)
    elif not WH_WHALE:
        # kdyby nebyl WH_WHALE, pošleme aspoň na fallback
        send_to_discord(msg)

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/hook")
async def hook(req: Request):
    try:
        body = await req.json()
    except Exception as e:
        print("❌ JSON parse error:", e)
        return {"status": "bad json"}

    # Helius někdy pošle pole; jindy jeden objekt
    items = body if isinstance(body, list) else [body]
    for tx in items:
        try:
            parse_and_alert(tx)
        except Exception as e:
            print("❌ parse_and_alert error:", e)
            # nevracíme 500, ať Helius ne-retryuje donekonečna

    return {"status": "ok"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
