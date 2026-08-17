# TheKClaut Telegram Bot 🇳🇬🇬🇭🇰🇪

SMM Panel reseller bot for **https://thekclaut.com** — Lets your Telegram users buy followers/likes/views automatically via the official API (`https://thekclaut.com/api/v2`).

> No scraping. 100% API-based. Stable, fast, Perfect Panel compatible.

---

## Features
- 💰 `/balance` live wallet (NGN/KES/GHS/USD)
- 📋 `/services` browse 500+ services by category with pagination + rates
- 🛒 `/order` interactive wizard: Service → Link → Quantity → Confirm
- 📊 `/status 12345` live order tracking (Partial/Completed/In progress)
- 📦 `/history` local SQLite history per Telegram user
- ♻️ `/refill 12345` & `/cancel 12345`
- 💸 Automatic markup support (resell at profit)
- 🔒 Validates URL, quantity min/max, public link, balance check

## Quick Start (5 minutes)

### 1. Create Telegram Bot
1. Open Telegram → search **@BotFather**
2. Send `/newbot` → choose name `KClautOrdersBot` → username `kclaut_orders_bot`
3. Copy the **BOT_TOKEN** (looks like `123456:AAH...`)

### 2. Get TheKClaut API Key
1. Sign up at https://thekclaut.com/signup (Lagos, NGN works)
2. Login → top menu → **API Key** (or Account → API Key)
3. Fund wallet small test (₦1000 via Paystack) for testing

### 3. Deploy Locally
```bash
git clone <this>  # or copy folder
cd thekclaut-telegram-bot
pip install -r requirements.txt
cp .env.example .env
# edit .env with nano or notepad
nano .env
python bot.py
```
You should see:
```
✅ Connected to TheKClaut API. Balance: 12.50 USD
✅ Loaded 847 services
🤖 Bot is polling... Press Ctrl+C to stop.
```

Open Telegram → send `/start` to your bot → Done!

### 4. Deploy to Cloud (24/7)
**Option A - Free: Railway / Render / Replit**
- Push to GitHub → Import to Railway.app → Add variables from .env → Deploy → logs show polling.

**Option B - VPS (Ubuntu)**
```bash
sudo apt update && sudo apt install python3-pip tmux -y
pip3 install -r requirements.txt
tmux new -s kclaut
python3 bot.py
# detach: Ctrl+B then D
```

**For Webhook (instead of polling)**: Change `app.run_polling()` to `app.run_webhook(...)` and set domain. Polling is recommended for beginners.

---

## Commands
```
/start - Welcome + wallet + buttons
/balance - Wallet
/services - Browse categories
/order - New order (wizard)
/status 123 - Check order
/history - My last orders
/cancel 123 - Cancel
/refill 123 - Refill dropped followers
/help - Help
```

## How the Wizard Works
1. User taps **🛒 New Order** or `/order`
2. Picks category (e.g., "Instagram Followers [Nigeria]")
3. Picks service `ID 123 - Followers NGN` (shows rate, min/max)
4. Sends link: `https://www.instagram.com/p/ABC123/` (must be public!)
5. Sends quantity: `1000` (between min/max)
6. Bot calculates price (rate * qty/1000 + markup), shows Confirm → `yes` → calls `POST /api/v2 action=add` → returns Order ID → saves to SQLite → user can `/status`

## Markup / Reselling
In `.env`:
```
MARKUP_PERCENT=30
```
If panel rate is $0.90/1k and user orders 1000 → you charge $1.17 → $0.27 profit per order. All profit stays in your panel wallet? Actually you need to collect from users separately (via Paystack/Flutterwave Opay link) — for MVP, manually top up panel wallet. For automation, add payment: integrate Paystack to let Telegram users fund their bot wallet first (ask me to add this!).

## Customization
- Edit `bot.py` → `start()` text, `MARKUP_PERCENT` logic, SQLite path
- Add Paystack funding: I can add `/addfunds` with Paystack inline
- Add admin panel: view all orders, broadcast

## Troubleshooting
- `Invalid API key` → Regenerate at thekclaut.com, update .env, restart
- `Not enough funds` → Top up at https://thekclaut.com/addfunds
- `Incorrect order ID` → Order not found, check ID
- Balance shows but services fail → API maybe rate-limited, wait 60s

## Safety Notes
- Private Instagram = no refund. Bot warns users.
- Rates change anytime without notice (panel Terms). Bot fetches live services each 5 min.
- Artificial engagement may violate Instagram ToS → add disclaimer (already included).

---

## Need Help?
Tell me:
- Your BOT_TOKEN and API_KEY (privately) and I can test live
- Want me to add **Paystack auto-funding** or **WhatsApp** version?

Built 17 Aug 2026 for Lagos — Optimized for NGN, M-Pesa, MoMo.

---
## Deploy to Render (One-Click)
[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/YOUR_USERNAME/kclaut-telegram-bot)
See `RENDER_GUIDE.md` for full steps with GitHub.
