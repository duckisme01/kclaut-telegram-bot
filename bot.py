#!/usr/bin/env python3
"""
TheKClaut Telegram Bot — SMM Panel Reseller Bot
Uses Official API: https://thekclaut.com/api/v2
Built for Nigeria/Ghana/Kenya - Supports NGN/KES/GHS/USD

Commands:
 /start - Welcome + balance
 /balance - Check wallet
 /services - Browse services by category
 /order - Start interactive order wizard
 /status <order_id> - Check single order
 /history - Your last 10 orders (local)
 /cancel <order_id> - Cancel order
 /refill <order_id> - Refill order
 /help - Help

Setup:
 1. Create bot via @BotFather -> get BOT_TOKEN
 2. Get API key from https://thekclaut.com (Dashboard -> API Key)
 3. cp .env.example .env and fill tokens
 4. pip install -r requirements.txt
 5. python bot.py
"""

import os
import re
import logging
import sqlite3
import asyncio
from datetime import datetime
from dotenv import load_dotenv

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, ContextTypes, filters
)
from telegram.constants import ParseMode

from thekclaut_api import TheKClautAPI

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_KEY = os.getenv("THEKCLAUT_API_KEY")
ADMIN_ID = os.getenv("ADMIN_ID")  # optional: your telegram id for admin alerts
MARKUP_PERCENT = float(os.getenv("MARKUP_PERCENT", "0"))  # e.g., 20 for 20% profit
CURRENCY = os.getenv("CURRENCY_LABEL", "USD")

# --- Fast mode: Instagram Views only (user requested) ---
DEFAULT_VIEWS_SERVICE = int(os.getenv("DEFAULT_VIEWS_SERVICE", "12263"))  # Instagram Views
REEL_VIEWS_SERVICE = int(os.getenv("REEL_VIEWS_SERVICE", "11953"))  # Instagram Reel Views

# --- Render health check server (needed for Web Service on Render) ---
def start_health_server():
    """Start tiny HTTP server for Render health checks so Web Service stays alive"""
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    port = int(os.getenv("PORT", "10000"))
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(f"OK - KClaut Bot running - {datetime.now().isoformat()}".encode())
        def log_message(self, format, *args):
            return  # silence
    def run():
        try:
            server = HTTPServer(("0.0.0.0", port), Handler)
            print(f"🌐 Health server listening on 0.0.0.0:{port} (for Render)")
            server.serve_forever()
        except Exception as e:
            print(f"Health server error: {e}")
    t = threading.Thread(target=run, daemon=True)
    t.start()

# Conversation states
CAT, SERVICE, LINK, QUANTITY, CONFIRM, QUICK_QTY, QUICK_CONFIRM = range(7)

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- DB for order history (sqlite) ---
DB_PATH = "orders.db"

def init_db():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER,
        username TEXT,
        order_id INTEGER,
        service_id INTEGER,
        service_name TEXT,
        link TEXT,
        quantity INTEGER,
        charge TEXT,
        currency TEXT,
        status TEXT,
        created_at TEXT
    )""")
    con.commit()
    con.close()

def save_order(telegram_id, username, order_id, service_id, service_name, link, quantity, charge, currency):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("INSERT INTO orders (telegram_id, username, order_id, service_id, service_name, link, quantity, charge, currency, status, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (telegram_id, username, order_id, service_id, service_name, link, quantity, str(charge) if charge else "", currency, "Pending", datetime.now().isoformat()))
    con.commit()
    con.close()

def get_history(telegram_id, limit=10):
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute("SELECT * FROM orders WHERE telegram_id=? ORDER BY id DESC LIMIT ?", (telegram_id, limit))
    rows = cur.fetchall()
    con.close()
    return rows

api = None

def format_price(rate_str):
    try:
        rate = float(rate_str)
        if MARKUP_PERCENT:
            rate = rate * (1 + MARKUP_PERCENT/100)
        # Show 4 decimals for USD, 2 for NGN etc.
        return f"{rate:.2f}"
    except:
        return rate_str

def escape_markdown(text: str):
    # simple escape for user input in markdown replies
    if not text:
        return ""
    return text.replace("_","\\_").replace("*","\\*").replace("`","\\`")

# --- Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    try:
        bal = api.get_balance()
        balance_str = f"{bal.get('balance')} {bal.get('currency', CURRENCY)}"
    except Exception as e:
        balance_str = f"⚠️ Could not fetch balance: {e}\nCheck THEKCLAUT_API_KEY in .env"
    text = (
        f"👋 *Welcome {escape_markdown(user.first_name)} to TheKClaut Bot* 🇳🇬🇬🇭🇰🇪\n\n"
        f"Cheapest SMM Panel in Africa — now on Telegram!\n"
        f"💰 *Wallet:* `{balance_str}`\n"
        f"{f'📈 *Your markup:* {MARKUP_PERCENT:.0f}% profit on each order' if MARKUP_PERCENT else ''}\n\n"
        f"*⚡ FAST MODE — Instagram Views Only:*\n"
        f"Just *drop your Instagram link* here and I'll auto-use Views!\n"
        f"• Regular post/video → Views `12263`\n"
        f"• Reel (`/reel/`) → Reel Views `11953` ✨ Auto-detected!\n\n"
        f"*What can I do?*\n"
        f"• Auto Views: drop link → send quantity → done!\n"
        f"• Still have: /services, /history, /status\n"
        f"• Refill & cancel supported\n\n"
        f"*Try it:* Send `https://www.instagram.com/p/ABC123/` or `https://www.instagram.com/reel/XYZ/` now!\n"
        f"Or tap *🛒 New Order* for the old menu.\n\n"
        f"⚠️ _Link must be public — private = no refund._\n"
    )
    keyboard = [
        [InlineKeyboardButton("🛒 New Order", callback_data="start_order"),
         InlineKeyboardButton("📋 Services", callback_data="browse_services")],
        [InlineKeyboardButton("💰 Balance", callback_data="check_balance"),
         InlineKeyboardButton("📦 My Orders", callback_data="my_history")],
        [InlineKeyboardButton("❓ Help", callback_data="help")]
    ]
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "*TheKClaut Bot — Commands*\n\n"
        "/start — Welcome & wallet\n"
        "/balance — Check balance\n"
        "/services — Browse services by category\n"
        "/order — Start new order wizard\n"
        "/status `12345` — Check order status\n"
        "/history — Last 10 orders\n"
        "/cancel `12345` — Cancel order(s)\n"
        "/refill `12345` — Refill order\n"
        "/help — This message\n\n"
        "*Order Wizard Tips:*\n"
        "• Link must be *public* (private = no refund!)\n"
        "• Quantity must be between min/max shown\n"
        "• For drip-feed: add runs+interval later via support\n\n"
        "*Support:* TheKClaut is online 16h/day. For failed orders, contact panel support with Order ID.\n"
    )
    if update.message:
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def balance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        bal = api.get_balance()
        text = f"💰 *Balance:* `{bal.get('balance')} {bal.get('currency')}`\n"
        if MARKUP_PERCENT:
            text += f"📈 Markup active: {MARKUP_PERCENT}%\n"
        text += "\nTop up at: https://thekclaut.com/addfunds"
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        err = f"❌ Balance error: `{escape_markdown(str(e))}`"
        if update.callback_query:
            await update.callback_query.answer(err, show_alert=True)
        else:
            await update.message.reply_text(err, parse_mode=ParseMode.MARKDOWN)

async def history_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = get_history(update.effective_user.id)
    if not rows:
        text = "📭 No orders yet. Use /order to create your first!"
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.message.reply_text(text)
        else:
            await update.message.reply_text(text)
        return
    text = "*📦 Your Last Orders:*\n\n"
    for r in rows:
        text += f"• `#{r['order_id']}` — {escape_markdown(r['service_name'][:30])} | {r['quantity']} | `{r['link'][:30]}...` | `{r['status']}` | {r['created_at'][:16]}\n"
    text += "\nCheck live status: `/status 12345`"
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/status 12345` or `/status 123,456` (up to 100)", parse_mode=ParseMode.MARKDOWN)
        return
    raw = " ".join(context.args)
    ids = re.findall(r"\d+", raw)
    if not ids:
        await update.message.reply_text("Please provide valid numeric Order ID(s).")
        return
    try:
        if len(ids) == 1:
            data = api.get_status(int(ids[0]))
            # update local DB if we have it
            status = data.get("status", "Unknown")
            remains = data.get("remains")
            charge = data.get("charge")
            currency = data.get("currency", "")
            text = (
                f"*📊 Order #{ids[0]}*\n"
                f"Status: *{escape_markdown(status)}*\n"
                f"Charge: `{charge} {currency}`\n"
                f"Start count: `{data.get('start_count')}`\n"
                f"Remains: `{remains}`\n"
            )
            if status == "Partial":
                text += "\n⚠️ *Partial* = not fully deliverable. Remaining funds refunded to wallet."
            elif status == "Completed":
                text += "\n✅ Completed!"
        else:
            data = api.get_multi_status(list(map(int, ids)))
            text = "*📊 Multiple Orders:*\n\n"
            for oid, info in data.items():
                if "error" in info:
                    text += f"• `#{oid}`: ❌ {escape_markdown(info['error'])}\n"
                else:
                    text += f"• `#{oid}`: *{escape_markdown(info['status'])}* | {info.get('charge')} {info.get('currency')} | remains {info.get('remains')}\n"
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await update.message.reply_text(f"❌ Error: `{escape_markdown(str(e))}`", parse_mode=ParseMode.MARKDOWN)

async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/cancel 12345` or `/cancel 123,456`", parse_mode=ParseMode.MARKDOWN)
        return
    ids = list(map(int, re.findall(r"\d+", " ".join(context.args))))
    try:
        res = api.cancel(ids)
        text = "*Cancel Request:*\n\n"
        # response is list of {order, cancel: 1 or error}
        if isinstance(res, list):
            for r in res:
                oid = r.get("order")
                c = r.get("cancel")
                if isinstance(c, dict) and "error" in c:
                    text += f"• `#{oid}`: ❌ {escape_markdown(c['error'])}\n"
                else:
                    text += f"• `#{oid}`: ✅ Cancel requested (`{c}`)\n"
        else:
            text += f"`{escape_markdown(str(res))}`"
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await update.message.reply_text(f"❌ Cancel error: `{escape_markdown(str(e))}`", parse_mode=ParseMode.MARKDOWN)

async def refill_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/refill 12345` — refill dropped followers if service supports refill", parse_mode=ParseMode.MARKDOWN)
        return
    oid = int(re.findall(r"\d+", " ".join(context.args))[0])
    try:
        res = api.refill(oid)
        # res = {"refill": "1"} or error
        if "refill" in res:
            await update.message.reply_text(f"✅ Refill created! Refill ID: `{res['refill']}`\nCheck with refill status later.", parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text(f"Response: `{escape_markdown(str(res))}`", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await update.message.reply_text(f"❌ Refill error: `{escape_markdown(str(e))}`", parse_mode=ParseMode.MARKDOWN)

# --- Services browsing ---
async def services_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        cats = api.get_categories()
        # show categories as buttons, 2 per row
        buttons = []
        row = []
        for cat in sorted(cats.keys())[:20]:  # limit to 20 cats
            count = len(cats[cat])
            row.append(InlineKeyboardButton(f"{cat} ({count})", callback_data=f"cat:{cat}"))
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        buttons.append([InlineKeyboardButton("🔄 Refresh", callback_data="browse_services_refresh")])
        text = f"*📋 Services* — {len(api.get_services())} total\nSelect a category:"
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(buttons))
        else:
            await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        err = f"❌ Services error: `{escape_markdown(str(e))}`"
        if update.callback_query:
            await update.callback_query.answer(err, show_alert=True)
        else:
            await update.message.reply_text(err, parse_mode=ParseMode.MARKDOWN)

async def category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cat = query.data.split(":",1)[1]
    try:
        cats = api.get_categories()
        services = cats.get(cat, [])
        # paginate 5 per page
        page = int(context.user_data.get(f"page_{cat}", 0))
        per_page = 6
        start = page * per_page
        chunk = services[start:start+per_page]

        text = f"*{escape_markdown(cat)}* — {len(services)} services (page {page+1}/{(len(services)-1)//per_page+1})\n\n"
        buttons = []
        for s in chunk:
            rate = format_price(s['rate'])
            name = s['name'][:40]
            # show key info
            text += f"`ID {s['service']}` *{escape_markdown(name)}* | `${rate}/1k` | min {s['min']} max {s['max']} {'♻️' if s.get('refill') else ''} {'❌' if not s.get('cancel') else ''}\n"
            buttons.append([InlineKeyboardButton(f"🛒 Order ID {s['service']} — {name[:22]}", callback_data=f"svc:{s['service']}")])

        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"cat:{cat}"))
            # we store page in user_data and mimic via callback
            context.user_data[f"page_{cat}"] = page - 1
        if start + per_page < len(services):
            nav.append(InlineKeyboardButton("➡️ Next", callback_data=f"cat:{cat}"))
            # hack: increment after? Instead use separate next handler
        # Simpler: use page param in callback
        # Rebuild nav with explicit page
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"page:{cat}:{page-1}"))
        if start + per_page < len(services):
            nav.append(InlineKeyboardButton("➡️ Next", callback_data=f"page:{cat}:{page+1}"))
        nav.append(InlineKeyboardButton("🔙 Categories", callback_data="browse_services"))
        if nav:
            buttons.append(nav)

        await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(buttons) if buttons else None)
        # store current page for next
        context.user_data[f"page_{cat}"] = page
    except Exception as e:
        await query.message.reply_text(f"❌ Error loading category: `{escape_markdown(str(e))}`", parse_mode=ParseMode.MARKDOWN)

async def page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, cat, page_str = query.data.split(":",2)
    page = int(page_str)
    context.user_data[f"page_{cat}"] = page
    # reuse category logic by faking callback
    query.data = f"cat:{cat}"
    await category_callback(update, context)

# --- Order wizard ---

async def order_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Entry via /order or button
    if update.callback_query:
        await update.callback_query.answer()
        # If user clicked a specific service
        if update.callback_query.data.startswith("svc:"):
            svc_id = int(update.callback_query.data.split(":")[1])
            context.user_data["service_id"] = svc_id
            # fetch service details
            try:
                services = api.get_services()
                svc = next((s for s in services if int(s["service"]) == svc_id), None)
                if not svc:
                    raise Exception("Service not found")
                context.user_data["service"] = svc
                rate = format_price(svc["rate"])
                text = (
                    f"*🛒 Order: {escape_markdown(svc['name'])}*\n"
                    f"Category: {escape_markdown(svc['category'])}\n"
                    f"Rate: `${rate}` / 1000 {f'(+{MARKUP_PERCENT}% markup included)' if MARKUP_PERCENT else ''}\n"
                    f"Min: `{svc['min']}`  Max: `{svc['max']}`\n"
                    f"Type: `{svc['type']}`  Refill: {'Yes' if svc.get('refill') else 'No'}\n\n"
                    f"Now send me the *LINK* to boost (must be public!):\n"
                    f"Example: `https://www.instagram.com/p/ABC123/`\n"
                )
                await update.callback_query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
                return LINK
            except Exception as e:
                await update.callback_query.message.reply_text(f"❌ Error: {escape_markdown(str(e))}")
                return ConversationHandler.END
        # generic start
        await services_cmd(update, context)
        await update.callback_query.message.reply_text("👆 Pick a category then a service, or send a Service ID directly (e.g., `123`).", parse_mode=ParseMode.MARKDOWN)
        return CAT

    # via command
    await update.message.reply_text(
        "🛒 *New Order* — Send me a *Service ID* or browse:\n"
        "Type `/services` to browse, or just send the ID (e.g., `123`)\n"
        "Or tap below:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📋 Browse Services", callback_data="browse_services")]])
    )
    return CAT

async def cat_state(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    # allow service ID directly
    if text.isdigit():
        svc_id = int(text)
        try:
            services = api.get_services()
            svc = next((s for s in services if int(s["service"]) == svc_id), None)
            if not svc:
                await update.message.reply_text(f"❌ Service ID {svc_id} not found. Try /services to browse.")
                return CAT
            context.user_data["service_id"] = svc_id
            context.user_data["service"] = svc
            rate = format_price(svc["rate"])
            await update.message.reply_text(
                f"*🛒 Selected: {escape_markdown(svc['name'])}*\n"
                f"Category: {escape_markdown(svc['category'])}\n"
                f"Rate: `${rate}`/1k  Min `{svc['min']}` Max `{svc['max']}`\n\n"
                f"Now send the *LINK*:",
                parse_mode=ParseMode.MARKDOWN
            )
            return LINK
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {escape_markdown(str(e))}")
            return ConversationHandler.END
    else:
        await update.message.reply_text("Please send a numeric Service ID, or tap 📋 Browse Services.")
        return CAT

async def link_state(update: Update, context: ContextTypes.DEFAULT_TYPE):
    link = update.message.text.strip()
    # basic URL validation
    if not re.match(r'^https?://', link):
        await update.message.reply_text("❌ Please send a valid URL starting with `https://`", parse_mode=ParseMode.MARKDOWN)
        return LINK
    context.user_data["link"] = link
    svc = context.user_data["service"]
    # if service type is Package or Subscription, quantity not needed
    svc_type = svc.get("type", "Default")
    if svc_type in ["Package", "Subscriptions"]:
        # For subscriptions need username etc. Simplified: ask quantity anyway or skip
        if svc_type == "Package":
            await update.message.reply_text(
                f"✅ Link saved.\nService `{escape_markdown(svc['name'])}` is *Package* — quantity is fixed. No quantity needed.\n"
                f"Send *confirm* to place order or *cancel* to abort.",
                parse_mode=ParseMode.MARKDOWN
            )
            context.user_data["quantity"] = None
            return CONFIRM
        else:
            await update.message.reply_text(
                "This is a *Subscription* service. For now, bot supports Default/Package. Please contact admin for subscriptions or choose another service via /order",
                parse_mode=ParseMode.MARKDOWN
            )
            return ConversationHandler.END

    # Check custom comments type
    if "Custom Comments" in svc_type or "Comment" in svc_type and svc_type != "Default":
        await update.message.reply_text(
            f"✅ Link saved.\n\nThis service needs *custom comments*.\n"
            f"Now send comments, each on new line:\n"
            f"`Great post!\\nLove this\\n🔥🔥`\n",
            parse_mode=ParseMode.MARKDOWN
        )
        # We'll treat next message as comments quantity? Actually need comments param not quantity
        context.user_data["expect_comments"] = True
        return QUANTITY

    await update.message.reply_text(
        f"✅ Link: `{escape_markdown(link)}`\n\n"
        f"Now send *quantity* (number between `{svc['min']}` and `{svc['max']}`):",
        parse_mode=ParseMode.MARKDOWN
    )
    context.user_data["expect_comments"] = False
    return QUANTITY

async def quantity_state(update: Update, context: ContextTypes.DEFAULT_TYPE):
    svc = context.user_data["service"]
    is_comments = context.user_data.get("expect_comments", False)
    text = update.message.text.strip()

    if is_comments:
        # text is comments list
        if len(text) < 3:
            await update.message.reply_text("❌ Please send at least one comment (each line = one comment).")
            return QUANTITY
        context.user_data["comments"] = text
        # for display, quantity = number of lines
        lines = [l for l in text.splitlines() if l.strip()]
        context.user_data["quantity_display"] = f"{len(lines)} comments"
        await update.message.reply_text(
            f"✅ {len(lines)} comments saved.\n\n"
            f"*Confirm order:*\n"
            f"Service: *{escape_markdown(svc['name'])}* (ID `{svc['service']}`)\n"
            f"Link: `{escape_markdown(context.user_data['link'])}`\n"
            f"Comments: `{escape_markdown(text[:60])}...`\n"
            f"Rate: `${format_price(svc['rate'])}/1k`\n\n"
            f"Type *yes* to confirm or *no* to cancel.",
            parse_mode=ParseMode.MARKDOWN
        )
        return CONFIRM

    # normal quantity
    if not text.isdigit():
        await update.message.reply_text("❌ Please send a numeric quantity (e.g., `1000`).")
        return QUANTITY
    qty = int(text)
    min_q = int(svc["min"])
    max_q = int(svc["max"])
    if qty < min_q or qty > max_q:
        await update.message.reply_text(f"❌ Quantity must be between `{min_q}` and `{max_q}`.", parse_mode=ParseMode.MARKDOWN)
        return QUANTITY
    # calculate price
    rate = float(svc["rate"])
    if MARKUP_PERCENT:
        rate = rate * (1 + MARKUP_PERCENT/100)
    price = rate * qty / 1000
    context.user_data["quantity"] = qty
    context.user_data["price"] = price

    await update.message.reply_text(
        f"*Confirm order:*\n"
        f"Service: *{escape_markdown(svc['name'])}* (ID `{svc['service']}`)\n"
        f"Link: `{escape_markdown(context.user_data['link'])}`\n"
        f"Quantity: `{qty}`\n"
        f"Price: *~${price:.2f} {CURRENCY}* (Rate `${format_price(svc['rate'])}/1k`)\n\n"
        f"Type *yes* to confirm or *no* to cancel. Also ensure link is *public*!",
        parse_mode=ParseMode.MARKDOWN
    )
    return CONFIRM

async def confirm_state(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().lower()
    if text not in ["yes", "y", "confirm", "ok"]:
        await update.message.reply_text("❌ Order cancelled. Use /order to start again.")
        context.user_data.clear()
        return ConversationHandler.END

    svc = context.user_data["service"]
    link = context.user_data["link"]
    qty = context.user_data.get("quantity")
    comments = context.user_data.get("comments")

    await update.message.reply_text("⏳ Placing order…")

    try:
        # check balance first
        bal = api.get_balance()
        # proceed
        if comments:
            res = api.create_order(service=int(svc["service"]), link=link, quantity=None, comments=comments)
        else:
            if qty is None:  # Package
                res = api.create_order(service=int(svc["service"]), link=link)
            else:
                res = api.create_order(service=int(svc["service"]), link=link, quantity=qty)

        order_id = res.get("order")
        if not order_id:
            raise Exception(f"Unexpected response: {res}")

        # try to get charge info via status
        try:
            status_info = api.get_status(int(order_id))
            charge = status_info.get("charge", "?")
            currency = status_info.get("currency", "")
        except:
            charge = context.user_data.get("price", "?")
            currency = CURRENCY

        save_order(update.effective_user.id, update.effective_user.username or update.effective_user.first_name,
                   int(order_id), int(svc["service"]), svc["name"], link, qty or 0, charge, currency)

        await update.message.reply_text(
            f"✅ *Order Placed!*\n\n"
            f"🆔 Order ID: `{order_id}`\n"
            f"Service: *{escape_markdown(svc['name'])}*\n"
            f"Link: `{escape_markdown(link)}`\n"
            f"{'Quantity: `'+str(qty)+'`' if qty else ''}\n"
            f"Charge: `{charge} {currency}`\n\n"
            f"Track: `/status {order_id}`\n"
            f"Refill (if drops): `/refill {order_id}`\n"
            f"History: /history",
            parse_mode=ParseMode.MARKDOWN
        )
        # notify admin
        if ADMIN_ID:
            try:
                await context.bot.send_message(chat_id=int(ADMIN_ID),
                    text=f"🛒 New order #{order_id} by @{update.effective_user.username or update.effective_user.id}\n{svc['name']} x{qty} -> {link}")
            except:
                pass

    except Exception as e:
        await update.message.reply_text(f"❌ Failed to place order: `{escape_markdown(str(e))}`\n\nCheck:\n• Balance sufficient? /balance\n• Link public & correct platform?\n• Quantity in range?\n\nTry /order again.", parse_mode=ParseMode.MARKDOWN)
    context.user_data.clear()
    return ConversationHandler.END

async def cancel_wizard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Wizard cancelled.")
    context.user_data.clear()
    return ConversationHandler.END

# --- FAST MODE: Drop link → auto Views (12263) / Reel Views (11953) ---
async def quick_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Triggered when user drops an Instagram link directly"""
    raw = update.message.text.strip()
    # extract first URL
    m = re.search(r'https?://\S+', raw)
    link = m.group(0) if m else raw
    # clean trailing punctuation
    link = link.rstrip(').,>]!*')
    is_reel = "/reel/" in link.lower() or "/reels/" in link.lower()
    service_id = REEL_VIEWS_SERVICE if is_reel else DEFAULT_VIEWS_SERVICE
    try:
        services = api.get_services()
        svc = next((s for s in services if int(s["service"]) == service_id), None)
        if not svc:
            # fallback: try to find by name if ID not found
            raise Exception(f"Service {service_id} not found. Check panel services.")
        context.user_data["service"] = svc
        context.user_data["link"] = link
        context.user_data["quick"] = True
        rate = format_price(svc["rate"])
        svc_name = svc["name"]
        kind = "🎬 Reel Views" if is_reel else "👁️ Views"
        text = (
            f"🔗 Got it! {kind}\n"
            f"Link: `{escape_markdown(link)}`\n"
            f"Service: *{escape_markdown(svc_name)}* (ID `{service_id}`)\n"
            f"Rate: `${rate}/1k` | Min `{svc['min']}` Max `{svc['max']}`\n\n"
            f"How many views? Send *quantity* (e.g., `1000`):"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎬 Switch to Reel 11953", callback_data=f"quick_switch:{REEL_VIEWS_SERVICE}"),
             InlineKeyboardButton("👁️ Switch to Views 12263", callback_data=f"quick_switch:{DEFAULT_VIEWS_SERVICE}")],
            [InlineKeyboardButton("❌ Cancel", callback_data="quick_cancel")]
        ])
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
        return QUICK_QTY
    except Exception as e:
        await update.message.reply_text(f"❌ Could not load service {service_id}: `{escape_markdown(str(e))}`", parse_mode=ParseMode.MARKDOWN)
        return ConversationHandler.END

async def quick_quantity_state(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text.isdigit():
        await update.message.reply_text("❌ Please send a number, e.g., `1000`", parse_mode=ParseMode.MARKDOWN)
        return QUICK_QTY
    qty = int(text)
    svc = context.user_data.get("service")
    if not svc:
        await update.message.reply_text("❌ Session expired. Drop your link again.")
        return ConversationHandler.END
    min_q = int(svc["min"])
    max_q = int(svc["max"])
    if qty < min_q or qty > max_q:
        await update.message.reply_text(f"❌ Quantity must be between `{min_q}` and `{max_q}`", parse_mode=ParseMode.MARKDOWN)
        return QUICK_QTY
    rate = float(svc["rate"])
    if MARKUP_PERCENT:
        rate = rate * (1 + MARKUP_PERCENT/100)
    price = rate * qty / 1000
    context.user_data["quantity"] = qty
    context.user_data["price"] = price
    await update.message.reply_text(
        f"*Confirm order:*\n"
        f"Service: *{escape_markdown(svc['name'])}* (ID `{svc['service']}`)\n"
        f"Link: `{escape_markdown(context.user_data['link'])}`\n"
        f"Quantity: `{qty}`\n"
        f"Price: *~${price:.2f} {CURRENCY}* (Rate `${format_price(svc['rate'])}/1k`)\n\n"
        f"Type *yes* to confirm or *no* to cancel.",
        parse_mode=ParseMode.MARKDOWN
    )
    return QUICK_CONFIRM

async def quick_confirm_state(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().lower()
    if text not in ["yes", "y", "confirm", "ok"]:
        await update.message.reply_text("❌ Order cancelled. Just drop a link again to restart.")
        context.user_data.clear()
        return ConversationHandler.END
    svc = context.user_data["service"]
    link = context.user_data["link"]
    qty = context.user_data["quantity"]
    await update.message.reply_text("⏳ Placing order…")
    try:
        res = api.create_order(service=int(svc["service"]), link=link, quantity=qty)
        order_id = res.get("order")
        if not order_id:
            raise Exception(f"Unexpected response: {res}")
        try:
            status_info = api.get_status(int(order_id))
            charge = status_info.get("charge", "?")
            currency = status_info.get("currency", "")
        except:
            charge = context.user_data.get("price", "?")
            currency = CURRENCY
        save_order(update.effective_user.id, update.effective_user.username or update.effective_user.first_name,
                   int(order_id), int(svc["service"]), svc["name"], link, qty, charge, currency)
        await update.message.reply_text(
            f"✅ *Order Placed!* 🎉\n\n"
            f"🆔 Order ID: `{order_id}`\n"
            f"Service: *{escape_markdown(svc['name'])}* (`{svc['service']}`)\n"
            f"Link: `{escape_markdown(link)}`\n"
            f"Quantity: `{qty}`\n"
            f"Charge: `{charge} {currency}`\n\n"
            f"Track: `/status {order_id}` | History: /history\n"
            f"Drop another link for next order! 👇",
            parse_mode=ParseMode.MARKDOWN
        )
        if ADMIN_ID:
            try:
                await context.bot.send_message(chat_id=int(ADMIN_ID),
                    text=f"⚡ Fast order #{order_id} by @{update.effective_user.username or update.effective_user.id}\n{svc['name']} x{qty} -> {link}")
            except:
                pass
    except Exception as e:
        await update.message.reply_text(f"❌ Failed: `{escape_markdown(str(e))}`\nCheck balance / link / quantity and try again.", parse_mode=ParseMode.MARKDOWN)
    context.user_data.clear()
    return ConversationHandler.END

async def quick_switch_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    svc_id = int(query.data.split(":")[1])
    try:
        services = api.get_services()
        svc = next((s for s in services if int(s["service"]) == svc_id), None)
        if not svc:
            await query.answer("Service not found", show_alert=True)
            return
        context.user_data["service"] = svc
        link = context.user_data.get("link", "your link")
        rate = format_price(svc["rate"])
        await query.message.reply_text(
            f"🔁 Switched to *{escape_markdown(svc['name'])}* (ID `{svc_id}`) — Rate `${rate}/1k` | Min `{svc['min']}` Max `{svc['max']}`\n\n"
            f"Now send *quantity* for `{escape_markdown(link[:40])}...`:",
            parse_mode=ParseMode.MARKDOWN
        )
        return QUICK_QTY
    except Exception as e:
        await query.message.reply_text(f"❌ Switch failed: `{escape_markdown(str(e))}`", parse_mode=ParseMode.MARKDOWN)
        return QUICK_QTY

async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data
    if data.startswith("quick_switch:"):
        await quick_switch_callback(update, context)
        return
    if data == "quick_cancel":
        await update.callback_query.answer()
        await update.callback_query.message.reply_text("❌ Cancelled. Drop a new link to start again.")
        context.user_data.clear()
        return
    if data == "start_order":
        return await order_entry(update, context)
    elif data == "browse_services" or data == "browse_services_refresh":
        if data == "browse_services_refresh":
            api.get_services(force_refresh=True)
        await services_cmd(update, context)
    elif data == "check_balance":
        await balance_cmd(update, context)
    elif data == "my_history":
        await history_cmd(update, context)
    elif data == "help":
        await help_cmd(update, context)
    elif data.startswith("cat:"):
        await category_callback(update, context)
    elif data.startswith("page:"):
        await page_callback(update, context)
    elif data.startswith("svc:"):
        # treat as order entry for that service
        return await order_entry(update, context)
    else:
        await update.callback_query.answer("Unknown action")

def main():
    global api
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN missing. Set in .env (get from @BotFather)")
        return
    if not API_KEY:
        print("❌ THEKCLAUT_API_KEY missing. Set in .env (from https://thekclaut.com account)")
        return

    # Fix for Python 3.13 / Render: ensure event loop exists before PTB
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    # Start health server for Render Web Service (only if PORT set)
    if os.getenv("PORT"):
        try:
            start_health_server()
        except Exception as e:
            print(f"⚠️ Health server failed to start (non-critical): {e}")

    init_db()
    api = TheKClautAPI(API_KEY)

    # test API on startup
    try:
        bal = api.get_balance()
        print(f"✅ Connected to TheKClaut API. Balance: {bal.get('balance')} {bal.get('currency')}")
        print(f"✅ Loaded {len(api.get_services())} services")
    except Exception as e:
        print(f"⚠️ API test failed: {e}")
        print("Bot will start but /balance and orders will fail until API key is valid.")

    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("balance", balance_cmd))
    app.add_handler(CommandHandler("services", services_cmd))
    app.add_handler(CommandHandler("history", history_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("cancel", cancel_cmd))
    app.add_handler(CommandHandler("refill", refill_cmd))

    # FAST MODE: Drop Instagram link → auto Views/Reel (NEW - user requested)
    quick_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & filters.Regex(r'https?://\S*instagram\.com\S*') & ~filters.COMMAND, quick_start)],
        states={
            QUICK_QTY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, quick_quantity_state),
                CallbackQueryHandler(quick_switch_callback, pattern=r"^quick_switch:"),
                CallbackQueryHandler(callback_router, pattern=r"^quick_cancel$")
            ],
            QUICK_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, quick_confirm_state)],
        },
        fallbacks=[CommandHandler("cancel", cancel_wizard)],
        allow_reentry=True
    )
    app.add_handler(quick_conv)

    # Order wizard (old - still available via /order)
    conv = ConversationHandler(
        entry_points=[
            CommandHandler("order", order_entry),
            CallbackQueryHandler(order_entry, pattern="^(start_order|svc:.*)$")
        ],
        states={
            CAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, cat_state)],
            LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, link_state)],
            QUANTITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, quantity_state)],
            CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_state)],
        },
        fallbacks=[CommandHandler("cancel", cancel_wizard)],
        allow_reentry=True
    )
    app.add_handler(conv)

    # Callback router for menus
    app.add_handler(CallbackQueryHandler(callback_router))

    # Fallback: any other callback
    # app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u,c: u.message.reply_text("Unknown command. Try /help")))

    print("🤖 Bot is polling... Press Ctrl+C to stop.")
    print("Try /start in Telegram")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
