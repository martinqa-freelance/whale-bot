import os, time, json, requests, math
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()
WH_WHALE = os.getenv("WH_WHALE")
WH_WATCH = os.getenv("WH_WATCH")
THRESH_SOL = float(os.getenv("THRESH_SOL", "500"))
BIRDEYE = os.getenv("BIRDEYE_API_KEY", "")

WATCHLIST = set()
if os.path.exists("watchlist.txt"):
    with open("watchlist.txt", "r", encoding="utf-8") as f:
        WATCHLIST = {x.strip() for x in f if x.strip()}

LOGFILE = "alerts.json"

def log(entry):
    try:
        db = json.load(open(LOGFILE,"r",encoding="utf-8"))
    except Exception:
        db = []
    db.append(entry)
    json.dump(db, open(LOGFILE,"w",encoding="utf-8"), ensure_ascii=False, indent=2)

def send(webhook, title, desc, color=5814783):
    requests.post(webhook, json={
        "username":"WhaleCaster",
        "embeds":[{"title":title,"description":desc,"color":color}]
    }, timeout=10)

def emoji_rating(mc_change_15m, liq_usd, is_renounced, is_new_token, vol_mult_5m):
    tags = ["🐋"]
    if mc_change_15m is not None and mc_change_15m >= 10 and liq_usd >= 50000: tags.append("🚀")
    if vol_mult_5m is not None and vol_mult_5m >= 3: tags.append("🔥")
    if (liq_usd is not None and liq_usd < 15000) or (is_new_token and not is_renounced): tags.append("💩")
    # unique order-preserving
    seen, out = set(), []
    for t in tags:
        if t not in seen: seen.add(t); out.append(t)
    return " ".join(out)

def pct_change(a,b):
    if a and b: return round((b-a)/a*100,2)
    return None

# ---- MOCK fetch; v ostré verzi napojíme Helius/Birdeye/Dexscreener ----
def fetch_trades():
    # sem přijde polling z API – tady je fake jeden obchod pro demo
    return [{
        "wallet":"SoLWalletAddrFAKE123",
        "token":"TokenAddrFAKE456",
        "symbol":"DUMPINU",
        "buy_sol": 777,
        "holders": 91,
        "mc_usd": 9999,
        "liq_usd": 33235,
        "dex_url":"https://dexscreener.com/solana/xxxxxxxx",
        "solscan_url":"https://solscan.io/token/xxxxxxxx",
        "entry_price": 0.0123,
        "current_price": 0.0117,
        "mc_change_15m": 8.2,
        "vol_mult_5m": 2.1,
        "is_renounced": False,
        "is_new_token": True,
        "ts": int(time.time())
    }]

def handle(tr):
    chg = pct_change(tr["entry_price"], tr["current_price"])
    rating = emoji_rating(tr["mc_change_15m"], tr["liq_usd"], tr["is_renounced"], tr["is_new_token"], tr["vol_mult_5m"])
    desc = (
        f"{rating} **Whale BUY Alert**\n"
        f"**BUY:** {tr['buy_sol']} SOL tokenu `{tr['symbol']}`\n"
        f"🔗 **Adresa:** [Solscan]({tr['solscan_url']})\n"
        f"👥 **Holders:** {tr['holders']} | **MC:** ${tr['mc_usd']:,} | **LQ:** ${tr['liq_usd']:,}\n"
        f"🔥 **DexScreener:** {tr['dex_url']}\n"
        + (f"📈 **{('+' if chg is not None and chg>=0 else '')}{chg}%** od nákupu" if chg is not None else "")
    )

    if tr["wallet"] in WATCHLIST and WH_WATCH:
        send(WH_WATCH, "Watchlist BUY", desc)
    if tr["buy_sol"] >= THRESH_SOL and WH_WHALE:
        send(WH_WHALE, "Whale BUY Alert", desc)

    log({"wallet":tr["wallet"],"token":tr["token"],"buy_sol":tr["buy_sol"],"ts":tr["ts"]})

def main():
    print("WhaleCaster 24/7 running…")
    while True:
        for tr in fetch_trades():
            handle(tr)
        time.sleep(5)

if __name__ == "__main__":
    main()
