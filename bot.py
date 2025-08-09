# bot.py
import os, json, requests
from fastapi import FastAPI, Request
from dotenv import load_dotenv

load_dotenv()
WH_WHALE = os.getenv("WH_WHALE")
WH_WATCH = os.getenv("WH_WATCH")
THRESH_SOL = float(os.getenv("THRESH_SOL", "500"))

WATCHLIST = set()
if os.path.exists("watchlist.txt"):
    with open("watchlist.txt", "r", encoding="utf-8") as f:
        WATCHLIST = {x.strip() for x in f if x.strip()}

app = FastAPI()

def send_embed(webhook, title, desc, color=5814783):
    try:
        requests.post(webhook, json={
            "username":"WhaleCaster",
            "embeds":[{"title":title,"description":desc,"color":color}]
        }, timeout=10)
    except Exception as e:
        print("Discord error:", e)

def pct(a,b):
    try:
        return round((b-a)/a*100, 2)
    except Exception:
        return None

def rating(liq_usd=None, mc_change_15m=None, vol_mult_5m=None, renounced=None, is_new=None):
    tags = ["🐋"]
    if mc_change_15m is not None and mc_change_15m >= 10 and (liq_usd or 0) >= 50000: tags.append("🚀")
    if vol_mult_5m is not None and vol_mult_5m >= 3: tags.append("🔥")
    if (liq_usd is not None and liq_usd < 15000) or (is_new and not renounced): tags.append("💩")
    # unique
    out, seen = [], set()
    for x in tags:
        if x not in seen: seen.add(x); out.append(x)
    return " ".join(out)

def parse_helius(payload: dict):
    """
    Helius Enhanced webhook (type: SWAP)
    Pokusíme se vytáhnout:
      - kupující wallet
      - token mint/symbol (pokud je v logs) – symbol může být None, to nevadí
      - amount v SOL (kolik SOL šlo ven za nákup)
      - dex url / solscan url
    """
    # defaulty
    buyer = None
    token_mint = None
    symbol = "UNKNOWN"
    sol_spent = 0.0

    # 1) zdrojová peněženka (většinou první signer)
    try:
        buyer = payload["accountData"][0]["account"]["pubkey"]
    except Exception:
        pass

    # 2) swap event – Helius dává parsed swap
    #   hledáme "nativeInput" nebo "nativeOutput" v lamport (1 SOL = 1e9)
    try:
        events = payload.get("events", {})
        swap = events.get("swap", {})
        # kolik SOL jsme utratili (nativeInput = SOL -> token)
        lamports_in  = swap.get("nativeInput", 0) or 0
        lamports_out = swap.get("nativeOutput", 0) or 0
        if lamports_in:
            sol_spent = lamports_in / 1_000_000_000
        elif lamports_out and lamports_out < 0:  # bezpečnostní fallback
            sol_spent = abs(lamports_out) / 1_000_000_000

        # cílový token mint
        token_mint = (swap.get("tokenOutput", {}) or {}).get("mint")
        if not token_mint:
            token_mint = (swap.get("tokenInput", {}) or {}).get("mint")

    except Exception as e:
        print("parse swap err:", e)

    # Dex/Solscan odkazy
    dex_url = f"https://dexscreener.com/solana/{token_mint}" if token_mint else "https://dexscreener.com/solana"
    solscan_url = f"https://solscan.io/token/{token_mint}" if token_mint else "https://solscan.io/tx/"+payload.get("signature","")

    return buyer, token_mint, symbol, sol_spent, dex_url, solscan_url

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/hook")
async def hook(req: Request):
    body = await req.json()
    # Helius umí poslat pole transakcí – pro jistotu bereme všechny
    items = body if isinstance(body, list) else [body]

    for tx in items:
        # filtrujeme jen SWAP
        if tx.get("type") != "SWAP":
            continue

        buyer, mint, symbol, sol_spent, dex_url, solscan_url = parse_helius(tx)
        if not buyer or sol_spent <= 0:
            continue

        # prah pro whale channel
        is_whale = sol_spent >= THRESH_SOL
        is_watch = buyer in WATCHLIST

        # (volitelně sem doplníme lookup holders/MC/LQ přes jiné API; teď placeholders)
        holders = "?"
        mc_usd  = "?"
        lq_usd  = "?"

        # rating (zatím bez market dat)
        tags = rating()

        desc = (
            f"{tags} **Whale BUY Alert**\n"
            f"**BUY:** {round(sol_spent,2)} SOL tokenu `{symbol}`\n"
            f"🔗 **Adresa:** [Solscan]({solscan_url})\n"
            f"👥 **Holders:** {holders} | **MC:** ${mc_usd} | **LQ:** ${lq_usd}\n"
            f"🔥 **DexScreener:** {dex_url}\n"
        )

        if is_watch and WH_WATCH:
            send_embed(WH_WATCH, "Watchlist BUY", desc)
        if is_whale and WH_WHALE:
            send_embed(WH_WHALE, "Whale BUY Alert", desc)

    return {"status": "ok"}
