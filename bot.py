import os
import requests
from fastapi import FastAPI, Request
import uvicorn

app = FastAPI()

DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")
MIN_SOL = 500  # filtr — jen velké obchody

def send_to_discord(message: str):
    if not DISCORD_WEBHOOK:
        print("⚠️ Chybí DISCORD_WEBHOOK v .env")
        return
    try:
        requests.post(DISCORD_WEBHOOK, json={"content": message})
    except Exception as e:
        print(f"❌ Chyba při odesílání do Discordu: {e}")

def safe_get(d, *keys, default=None):
    """Bezpečné získání hodnoty z vnořeného dictu"""
    for k in keys:
        if isinstance(d, dict) and k in d:
            d = d[k]
        else:
            return default
    return d

def parse_swap(event):
    try:
        from_token = safe_get(event, "sourceMint") or "Unknown"
        to_token = safe_get(event, "destinationMint") or "Unknown"

        sol_amount = safe_get(event, "nativeInput", "amount") or 0
        sol_amount /= 1e9  # lamports → SOL

        # filtr na velké obchody
        if sol_amount < MIN_SOL:
            return None

        tx_hash = safe_get(event, "signature", default="N/A")
        return f"🐋 **Whale SWAP**: {sol_amount:.2f} SOL → {to_token}\nTx: {tx_hash}"

    except Exception as e:
        print(f"parse_swap err: {e}")
        return None

def parse_transfer(event):
    try:
        sol_amount = safe_get(event, "nativeAmount", "amount") or 0
        sol_amount /= 1e9

        if sol_amount < MIN_SOL:
            return None

        sender = safe_get(event, "fromUserAccount") or "Unknown"
        receiver = safe_get(event, "toUserAccount") or "Unknown"
        tx_hash = safe_get(event, "signature", default="N/A")

        return f"💸 **Whale Transfer**: {sol_amount:.2f} SOL\nFrom: {sender}\nTo: {receiver}\nTx: {tx_hash}"
    except Exception as e:
        print(f"parse_transfer err: {e}")
        return None

def parse_helius(payload):
    events = payload.get("events", [])
    messages = []

    for event in events:
        event_type = event.get("type", "").upper()

        if event_type == "SWAP":
            msg = parse_swap(event)
        elif event_type == "TRANSFER":
            msg = parse_transfer(event)
        else:
            msg = None  # ignorujeme ostatní

        if msg:
            messages.append(msg)

    return messages

@app.post("/hook")
async def hook(request: Request):
    payload = await request.json()
    msgs = parse_helius(payload)
    for m in msgs:
        send_to_discord(m)
    return {"status": "ok"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)