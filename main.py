import os
import logging
import random
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, ConversationHandler, CallbackQueryHandler, MessageHandler, filters
import database as db

# Load environment variables
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x]

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# States for Registration Conversation
ASK_EVENT, ASK_NEULING, ASK_PARTNER_CONFIRM, ASK_PARTNER_NAME = range(4)

def find_partner(partner_name, all_registrations):
    if not partner_name:
        return None
    partner_name = partner_name.lower().strip()
    # Remove @ if present
    if partner_name.startswith('@'):
        partner_name = partner_name[1:]
        
    for reg in all_registrations:
        if reg['full_name'].lower().strip() == partner_name:
            return reg
        if reg['username'] and reg['username'].lower().strip() == partner_name:
            return reg
    return None

def escape_md(text):
    if not text:
        return ""
    return text.replace("_", "\\_").replace("*", "\\*").replace("`", "\\`").replace("[", "\\[")

async def create_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        return
    
    if update.effective_chat.type != 'private':
        await update.message.reply_text("Please perform admin actions in a private chat.")
        return
    
    if not context.args:
        await update.message.reply_text("Verwendung: /create_event <Event Name>")
        return
        
    name = " ".join(context.args)
    # Default seat limit is 35
    event_id = db.create_event(name, seat_limit=35)
    await update.message.reply_text(f"Event '{name}' erstellt mit ID {event_id}. Sitzplatzlimit: 35")

async def admin_open(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        return

    if update.effective_chat.type != 'private':
        await update.message.reply_text("Bitte führe Admin-Aktionen im privaten Chat aus.")
        return
    
    events = db.get_events()
    # Filter for closed events
    closed_events = [e for e in events if not e['is_open']]
    
    if not closed_events:
        await update.message.reply_text("Keine geschlossenen Events zum Öffnen gefunden.")
        return
        
    keyboard = []
    for e in closed_events:
        keyboard.append([InlineKeyboardButton(e['name'], callback_data=f"admin_open_{e['id']}")])
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Wähle ein Event zum ÖFFNEN:", reply_markup=reply_markup)

async def admin_close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        return

    if update.effective_chat.type != 'private':
        await update.message.reply_text("Bitte führe Admin-Aktionen im privaten Chat aus.")
        return
    
    events = db.get_events()
    # Filter for open events
    open_events = [e for e in events if e['is_open']]
    
    if not open_events:
        await update.message.reply_text("Keine offenen Events zum Schließen gefunden.")
        return
        
    keyboard = []
    for e in open_events:
        keyboard.append([InlineKeyboardButton(e['name'], callback_data=f"admin_close_{e['id']}")])
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Wähle ein Event zum SCHLIESSEN:", reply_markup=reply_markup)

async def admin_event_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    action, event_id = data.rsplit('_', 1)
    event_id = int(event_id)
    event = db.get_event(event_id)
    
    if not event:
        await query.edit_message_text("Event nicht gefunden.")
        return

    if action == 'admin_open':
        db.set_event_open(event_id, True)
        await query.edit_message_text(f"Registrierung für '{event['name']}' ist jetzt GEÖFFNET.")
        
    elif action == 'admin_close':
        db.set_event_open(event_id, False)
        await query.edit_message_text(f"Registrierung für '{event['name']}' GESCHLOSSEN. Berechne Plätze...")
        await perform_allocation(update, context, event_id)
        
    elif action == 'admin_list':
        registrations = db.get_event_registrations(event_id)
        if not registrations:
            await query.edit_message_text(f"Keine Registrierungen für '{event['name']}' gefunden.")
            return

        count = 0
        for reg in registrations:
            count += 1
            if reg['partner_name']:
                # Check if partner is registered separately to avoid double counting
                partner_reg = find_partner(reg['partner_name'], registrations)
                if not partner_reg:
                    count += 1
                # If partner IS registered, they will be counted when their own entry is processed
                # However, we need to be careful not to double count if we iterate all.
                # Actually, if both registered, they are 2 entries = 2 count.
                # If only one registered + partner name, that is 1 entry but should be 2 count.
                # Correct logic:
                # If partner_name is present AND partner is NOT in the list as a separate user, add +1.
        
        msg = f"📋 *Registrierungen für {event['name']} ({count} Plätze):*\n\n"
        for reg in registrations:
            icon = "✅" if reg['status'] == 'ACCEPTED' else "⏳" if reg['status'] == 'PENDING' else "❌" if reg['status'] == 'CANCELLED' else "📝"
            safe_name = escape_md(reg['full_name'])
            safe_username = escape_md(reg['username'])
            safe_partner = escape_md(reg['partner_name'])
            
            partner_str = f" (Begleitung: {safe_partner})" if safe_partner else ""
            neuling = " [Neuling]" if reg['is_neuling'] else ""
            admin = " [Admin]" if reg['is_admin'] else ""
            
            line = f"{icon} {safe_name} (@{safe_username}){partner_str}{neuling}{admin} - {reg['status']}\n"
            if len(msg) + len(line) > 4000:
                logging.info(f"Sending chunk: {msg}")
                await context.bot.send_message(chat_id=query.message.chat_id, text=msg, parse_mode='Markdown')
                msg = ""
            msg += line
            
        if msg:
            logging.info(f"Sending final chunk: {msg}")
            try:
                await query.edit_message_text(msg, parse_mode='Markdown')
            except Exception as e:
                logging.error(f"Edit failed: {e}")
                # Fallback to send if edit fails (e.g. message too long or same content)
                await context.bot.send_message(chat_id=query.message.chat_id, text=msg, parse_mode='Markdown')

async def perform_allocation(update: Update, context: ContextTypes.DEFAULT_TYPE, event_id):
    # Allocation Logic
    all_regs = db.get_pending_registrations(event_id)
    # Convert to list of dicts for easier handling
    pending = [dict(r) for r in all_regs]
    
    accepted_ids = set()
    event = db.get_event(event_id)
    seats_limit = event['seat_limit']
    seats_taken = 0
    
    def accept(reg):
        nonlocal seats_taken
        if reg['user_id'] in accepted_ids:
            return
        accepted_ids.add(reg['user_id'])
        seats_taken += 1
        db.update_status(reg['user_id'], event_id, 'ACCEPTED')
    
    # 1. Admins
    admins = [r for r in pending if r['is_admin']]
    for r in admins:
        if r['user_id'] in accepted_ids:
            continue
            
        partner_reg = find_partner(r['partner_name'], pending)
        if r['partner_name'] and not partner_reg:
             # Partner not registered, but counts as seat
             accept(r)
             seats_taken += 1
        elif partner_reg:
             accept(r)
             accept(partner_reg)
        else:
             accept(r)
            
    # 2. Neulings
    neulings = [r for r in pending if r['is_neuling'] and r['user_id'] not in accepted_ids]
    for r in neulings:
        if r['user_id'] in accepted_ids:
            continue

        partner_reg = find_partner(r['partner_name'], pending)
        if r['partner_name'] and not partner_reg:
             # Partner not registered, but counts as seat
             accept(r)
             seats_taken += 1
        elif partner_reg:
             accept(r)
             accept(partner_reg)
        else:
             accept(r)
            
    # 3. Random
    remaining = [r for r in pending if r['user_id'] not in accepted_ids]
    random.shuffle(remaining)
    
    for r in remaining:
        if seats_taken >= seats_limit:
            break
        
        if r['user_id'] in accepted_ids:
            continue
            
        # Check if user has a partner (registered or just named)
        has_partner = bool(r['partner_name'])
        
        if has_partner:
            # Check if partner is also registered
            partner_reg = find_partner(r['partner_name'], pending)
            
            if partner_reg:
                # Partner is registered separately
                if partner_reg['user_id'] in accepted_ids:
                    # Partner already accepted, just accept this one
                    if seats_taken + 1 <= seats_limit:
                        accept(r)
                else:
                    # Both need acceptance
                    if seats_taken + 2 <= seats_limit:
                        accept(r)
                        accept(partner_reg)
            else:
                # Partner is NOT registered (just a name)
                # We still count them as a seat!
                if seats_taken + 2 <= seats_limit:
                    accept(r)
                    seats_taken += 1 # Extra seat for the non-registered partner
        else:
            # Single user
            if seats_taken + 1 <= seats_limit:
                accept(r)
    
    # 4. Waiting List
    for r in pending:
        if r['user_id'] not in accepted_ids:
            db.update_status(r['user_id'], event_id, 'WAITING')
            try:
                await context.bot.send_message(chat_id=r['user_id'], text=f"⏳ Registrierung für '{event['name']}' geschlossen.\n\nDu bist auf der *WARTELISTE*. Wir benachrichtigen dich, falls ein Platz frei wird! 🤞")
            except Exception as e:
                logging.error(f"Failed to send message to {r['user_id']}: {e}")

    # Notify Accepted
    for uid in accepted_ids:
        try:
            # Find registration to check for partner
            reg = next((r for r in pending if r['user_id'] == uid), None)
            msg = f"🎉 *Glückwunsch!* 🎉\n\nDu hast einen Platz für '{event['name']}'! Wir freuen uns auf dich! 🙌"
            
            if reg and reg['partner_name']:
                partner_reg = find_partner(reg['partner_name'], pending)
                if not partner_reg:
                    # Partner was not registered, so we inform the user they are both in
                    msg += f"\n\n👥 Deine Begleitung ({reg['partner_name']}) ist auch dabei!"
            
            await context.bot.send_message(chat_id=uid, text=msg)
        except Exception as e:
            logging.error(f"Failed to send message to {uid}: {e}")
            
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Zuteilung für '{event['name']}' abgeschlossen. {seats_taken} Plätze vergeben.")

async def admin_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        return

    if update.effective_chat.type != 'private':
        await update.message.reply_text("Please perform admin actions in a private chat.")
        return

    events = db.get_events()
    if not events:
        await update.message.reply_text("Keine Events gefunden.")
        return

    keyboard = []
    for e in events:
        keyboard.append([InlineKeyboardButton(e['name'], callback_data=f"admin_list_{e['id']}")])
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Wähle ein Event, um die Registrierungen zu sehen:", reply_markup=reply_markup)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):


    await update.message.reply_text(
        "Willkommen beim WHIP Wizard Bot! 🧙‍♂️\n\n"
        "Hier ist eine kurze Anleitung:\n"
        "1️⃣ **Registrieren**: Nutze /register, um dich für ein Event anzumelden. Du kannst angeben, ob du neu bist ('Neuling') und ob du jemanden mitbringst.\n"
        "2️⃣ **Status prüfen**: Mit /status siehst du, für welche Events du angemeldet bist und ob du einen Platz hast.\n"
        "3️⃣ **Abmelden**: Falls du doch nicht kannst, nutze /cancel, um deinen Platz freizugeben.\n\n"
        "Viel Spaß!"
    )

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if update.effective_chat.type != 'private':
        bot_username = context.bot.username
        await update.message.reply_text(f"Bitte registriere dich privat bei mir: t.me/{bot_username}?start=register")
        return ConversationHandler.END

    events = db.get_events()
    open_events = [e for e in events if e['is_open']]
    
    if not open_events:
        await update.message.reply_text("Aktuell sind keine Events für die Registrierung geöffnet.")
        return ConversationHandler.END
        
    if len(open_events) == 1:
        context.user_data['event_id'] = open_events[0]['id']
        context.user_data['event_name'] = open_events[0]['name']
        return await ask_neuling(update, context)
    
    # Multiple events
    keyboard = []
    for e in open_events:
        keyboard.append([InlineKeyboardButton(e['name'], callback_data=f"event_{e['id']}")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Bitte wähle ein Event für die Registrierung:", reply_markup=reply_markup)
    return ASK_EVENT

async def event_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    event_id = int(query.data.split('_')[1])
    event = db.get_event(event_id)
    
    if not event or not event['is_open']:
        await query.edit_message_text("Dieses Event ist nicht mehr geöffnet.")
        return ConversationHandler.END
        
    context.user_data['event_id'] = event_id
    context.user_data['event_name'] = event['name']
    
    await query.edit_message_text(f"Ausgewählt: {event['name']}")
    return await ask_neuling(update, context)

async def ask_neuling(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    event_id = context.user_data['event_id']
    
    existing = db.get_registration(user.id, event_id)
    if existing:
        msg = "Du bist bereits für dieses Event registriert."
        if update.callback_query:
            await update.callback_query.message.reply_text(msg)
        else:
            await update.message.reply_text(msg)
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("Ja", callback_data='neuling_yes')],
        [InlineKeyboardButton("Nein", callback_data='neuling_no')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    msg = "Bist du ein 'Neuling'?"
    if update.callback_query:
        await update.callback_query.message.reply_text(msg, reply_markup=reply_markup)
    else:
        await update.message.reply_text(msg, reply_markup=reply_markup)
        
    return ASK_NEULING

async def neuling_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    context.user_data['is_neuling'] = (query.data == 'neuling_yes')
    await query.edit_message_text(text=f"Neuling: {'Ja' if context.user_data['is_neuling'] else 'Nein'}")
    

    
    keyboard = [
        [InlineKeyboardButton("Ja", callback_data='partner_yes')],
        [InlineKeyboardButton("Nein", callback_data='partner_no')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.reply_text(
        "Bringst du eine weitere Person mit?",
        reply_markup=reply_markup
    )
    return ASK_PARTNER_CONFIRM

async def partner_confirm_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    has_partner = (query.data == 'partner_yes')
    
    if has_partner:
        await query.edit_message_text("Bringst du eine weitere Person mit? Ja")
        await query.message.reply_text(
            "Bitte gib den Telegram-Nutzernamen (beginnend mit @) oder den vollen Namen der Person ein."
        )
        return ASK_PARTNER_NAME
    else:
        await query.edit_message_text("Bringst du eine weitere Person mit? Nein")
        # No partner, proceed to finish registration
        return await finish_registration(update, context, partner_name=None)

async def partner_name_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    partner_name = update.message.text
    
    # Handle commands manually since we are capturing all TEXT
    if partner_name.startswith('/'):
        if partner_name == '/cancel':
            return await cancel(update, context)
        await update.message.reply_text("Bitte gib den Namen der Person ein. Verwende keine Befehle (außer /cancel).")
        return ASK_PARTNER_NAME
        
    return await finish_registration(update, context, partner_name)

async def finish_registration(update: Update, context: ContextTypes.DEFAULT_TYPE, partner_name):
    user = update.effective_user
    is_neuling = context.user_data.get('is_neuling', False)
    event_id = context.user_data.get('event_id')
    
    # Save to DB
    try:
        success = db.add_registration(user.id, event_id, user.username, user.full_name, is_neuling, partner_name)
    except Exception as e:
        logging.error(f"DB Error: {e}")
        success = False
    
    if success:
        # Check if user is admin
        if user.id in ADMIN_IDS:
            db.set_admin(user.id, event_id, True)
            
        msg = (
            "✅ *Registrierung erfolgreich!* ✅\n\n"
            "📝 Du wurdest zur *WARTELISTE* hinzugefügt.\n\n"
            "🔔 Du wirst benachrichtigt, sobald die Registrierung schließt und die Plätze vergeben sind!"
        )
        if partner_name:
            msg += f"\n\n👥 Begleitung registriert: {partner_name}"
            
        if update.callback_query:
             await update.callback_query.message.reply_text(msg, parse_mode='Markdown')
        else:
             await update.message.reply_text(msg, parse_mode='Markdown')
    else:
        if update.callback_query:
             await update.callback_query.message.reply_text("Ein Fehler ist während der Registrierung aufgetreten.")
        else:
             await update.message.reply_text("Ein Fehler ist während der Registrierung aufgetreten.")
        
    return ConversationHandler.END

async def notify_next_waiting(context: ContextTypes.DEFAULT_TYPE, event_id):
    waiting_list = db.get_waiting_list(event_id)
    if not waiting_list:
        return

    next_person = waiting_list[0]
    db.update_status(next_person['user_id'], event_id, 'OFFERED')
    
    event = db.get_event(event_id)
    
    keyboard = [
        [InlineKeyboardButton("Annehmen", callback_data=f'offer_accept_{event_id}')],
        [InlineKeyboardButton("Ablehnen", callback_data=f'offer_deny_{event_id}')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await context.bot.send_message(
            chat_id=next_person['user_id'],
            text=f"Ein Platz für '{event['name']}' ist frei geworden! Möchtest du ihn annehmen?",
            reply_markup=reply_markup
        )
    except Exception as e:
        logging.error(f"Failed to notify {next_person['user_id']}: {e}")

async def offer_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    action, event_id = data.rsplit('_', 1)
    event_id = int(event_id)
    
    user = update.effective_user
    reg = db.get_registration(user.id, event_id)
    
    if not reg or reg['status'] != 'OFFERED':
        await query.edit_message_text("Dieses Angebot ist nicht mehr gültig.")
        return

    if action == 'offer_accept':
        db.update_status(user.id, event_id, 'ACCEPTED')
        await query.edit_message_text("Du hast den Platz angenommen! Wir sehen uns.")
    else:
        db.update_status(user.id, event_id, 'DECLINED')
        await query.edit_message_text("Du hast den Platz abgelehnt.")
        # Notify next
        await notify_next_waiting(context, event_id)

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    regs = db.get_user_registrations(user.id)
    if not regs:
        await update.message.reply_text("Du bist für keine Events registriert.")
    else:
        msg = "*Deine Registrierungen:*\n"
        for r in regs:
            msg += f"- {r['event_name']}: {r['status']}\n"
        await update.message.reply_text(msg, parse_mode='Markdown')

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    regs = db.get_user_registrations(user.id)
    # Filter for active registrations (not cancelled or declined)
    active_regs = [r for r in regs if r['status'] not in ['CANCELLED', 'DECLINED']]
    
    if not active_regs:
        await update.message.reply_text("Du hast keine aktiven Registrierungen zum Stornieren.")
        return

    if len(active_regs) == 1:
        await perform_cancel(update, context, active_regs[0])
    else:
        keyboard = []
        for r in active_regs:
            keyboard.append([InlineKeyboardButton(r['event_name'], callback_data=f"cancel_{r['event_id']}")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Wähle ein Event zum Stornieren:", reply_markup=reply_markup)

async def cancel_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    event_id = int(query.data.split('_')[1])
    user = update.effective_user
    reg = db.get_registration(user.id, event_id)
    
    if not reg:
        await query.edit_message_text("Registrierung nicht gefunden.")
        return
        
    await perform_cancel(update, context, reg)

async def perform_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE, reg):
    user_id = reg['user_id']
    event_id = reg['event_id']
    
    if reg['status'] == 'CANCELLED':
        msg = "Du bist bereits storniert."
        if update.callback_query:
            await update.callback_query.edit_message_text(msg)
        else:
            await update.message.reply_text(msg)
        return

    was_accepted = (reg['status'] == 'ACCEPTED')
    db.update_status(user_id, event_id, 'CANCELLED')
    
    msg = "Registrierung storniert."
    if update.callback_query:
        await update.callback_query.edit_message_text(msg)
    else:
        await update.message.reply_text(msg)
    
    if was_accepted:
        await notify_next_waiting(context, event_id)

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Registrierung abgebrochen.")
    return ConversationHandler.END

if __name__ == '__main__':
    db.init_db()
    
    if not TOKEN:
        print("Error: TELEGRAM_TOKEN not found in .env")
        exit(1)
        
    application = ApplicationBuilder().token(TOKEN).build()
    
    reg_handler = ConversationHandler(
        entry_points=[CommandHandler('register', register)],
        states={
            ASK_EVENT: [CallbackQueryHandler(event_response, pattern='^event_')],
            ASK_NEULING: [CallbackQueryHandler(neuling_response)],
            ASK_PARTNER_CONFIRM: [CallbackQueryHandler(partner_confirm_response)],
            ASK_PARTNER_NAME: [MessageHandler(filters.TEXT, partner_name_response)]
        },
        fallbacks=[CommandHandler('cancel', cancel_conversation)]
    )
    
    application.add_handler(CommandHandler('start', start))
    application.add_handler(reg_handler)
    application.add_handler(CommandHandler('cancel', cancel))
    application.add_handler(CommandHandler('status', status))
    application.add_handler(CommandHandler('admin_open', admin_open))
    application.add_handler(CommandHandler('admin_close', admin_close))
    application.add_handler(CommandHandler('admin_list', admin_list))
    application.add_handler(CommandHandler('create_event', create_event))
    application.add_handler(CallbackQueryHandler(admin_event_response, pattern='^admin_'))
    application.add_handler(CallbackQueryHandler(offer_response, pattern='^offer_'))
    application.add_handler(CallbackQueryHandler(cancel_response, pattern='^cancel_'))
    
    print("Bot is running...")
    application.run_polling()
