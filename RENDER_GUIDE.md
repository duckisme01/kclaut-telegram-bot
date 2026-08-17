# Deploy to Render — Step-by-Step (5 minutes) 🇳🇬

Your bot is Render-ready (has health server on PORT 10000). Follow these exact clicks.

---

### OPTION A: Deploy via GitHub (Recommended, 1-click auto-deploy)

#### Step 1 — Push to GitHub
1. Create a new GitHub repo: https://github.com/new
   - Name: `kclaut-telegram-bot`
   - **Private** (important - contains your .env keys if you push it) → better to keep .env out of GitHub
   - Click **Create repository**

2. On your computer (where you unzipped):
```bash
cd thekclaut-telegram-bot
git init
git add bot.py thekclaut_api.py requirements.txt render.yaml README.md
# DO NOT add .env with real keys! Add .env.example instead
git add .env.example
git commit -m "Initial bot"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/kclaut-telegram-bot.git
git push -u origin main
```
> **Critical:** Do NOT `git add .env` with your real BOT_TOKEN — you'll leak keys. We'll add keys in Render dashboard securely.

#### Step 2 — Create Render Service
1. Go to **https://dashboard.render.com** → **New +** → **Web Service**
2. Connect your GitHub → Select `kclaut-telegram-bot` → **Connect**
3. Fill:
   - **Name:** `kclaut-telegram-bot`
   - **Region:** `Singapore` (closest to Lagos) or `Frankfurt`
   - **Branch:** `main`
   - **Runtime:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python bot.py`
   - **Plan:** `Free`

4. Scroll to **Environment** → **Add Environment Variable**:
   ```
   BOT_TOKEN = 8832064618:AAGeZz-SXybiM3oGVvzIB1m0B-gnWkIH0og
   THEKCLAUT_API_KEY = 00b4f1f69b6ca1f5c9bdae83e190366a
   MARKUP_PERCENT = 0
   CURRENCY_LABEL = NGN
   PORT = 10000
   ```
   (Paste your exact values from .env)

5. Click **Create Web Service** → Wait 2-3 mins for deploy → Logs should show:
   ```
   ✅ Connected to TheKClaut API. Balance: 71.477 NGN
   ✅ Loaded 307 services
   🌐 Health server listening on 0.0.0.0:10000
   🤖 Bot is polling...
   ```
6. Test: Send `/start` to `@viewsssssforguysbot` on Telegram → should reply instantly!

---

### OPTION B: Deploy without GitHub (Manual Upload via Render)

If you don't have GitHub:

1. Render Dashboard → **New +** → **Web Service** → Instead of GitHub, choose **Public Git repository** → paste any repo URL, OR use **“Deploy from existing image”** not ideal.

Better: Use **Render’s Blueprint** with `render.yaml`:
- Push `render.yaml` to GitHub as above → Render auto-detects blueprint → **New +** → **Blueprint** → Connect repo → **Apply**

Alternative without Git: Use **https://render.com/docs/deploy-without-github** or deploy to **Railway** which allows manual zip upload. For pure zip deploy, consider **Koyeb** or **Fly.io** — Render requires GitHub.

**Quick workaround - Use Railway for zip:**
- railway.app → New Project → Deploy via CLI: `railway up` after `npm i -g @railway/cli`

---

### FREE TIER WARNINGS (Render)

- **Free Web Service sleeps after 15 mins of no HTTP traffic** — but your bot still polls Telegram, so it gets HTTP health checks internally. Render will keep it alive but may sleep. If bot sleeps, first Telegram message after sleep takes ~30s to wake.
  - Fix: Use **UptimeRobot** (free): https://uptimerobot.com → Add monitor → URL = `https://kclaut-telegram-bot.onrender.com` → ping every 5 mins → keeps Render awake.

- **750 hours/month free** — enough for 1 service 24/7.

- **Logs:** Render Dashboard → Your Service → **Logs** → live tail. Check for errors.

---

### How to Update Bot Later

```bash
# Edit bot.py locally
git add bot.py
git commit -m "update"
git push origin main
# Render auto-redeploys!
```

### How to Change Markup / Keys on Render

Dashboard → Your Service → **Environment** → Edit `MARKUP_PERCENT` → **Save Changes** → auto-restart.

### Troubleshooting on Render

- **“No open ports detected”** → Fixed: bot now has health server on PORT. Ensure `PORT=10000` env var is set.
- **“Invalid API key”** → Check THEKCLAUT_API_KEY in Render Environment matches thekclaut.com Dashboard.
- **Bot not replying** → Check Logs tab → look for `Application started` and `polling`. If shows `Conflict: terminated by other getUpdates`, you have bot running in TWO places (workspace + Render). Stop workspace one: run `stop_process` or stop local `python bot.py`.
- **Balance not showing** → Ensure `THEKCLAUT_API_KEY` has no extra spaces.

---

### Need Help?

Tell me:
1. Do you have a GitHub username? I'll give you exact `git push` command with your username.
2. Do you want me to make a **clean zip without keys** for GitHub push? (I have your real zip ready, but for GitHub you need clean one)

Want me to also generate a **one-click Deploy to Render button** for your GitHub README?
