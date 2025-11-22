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
        await update.message.reply_text("Usage: /create_event <Event Name>")
        return
        
    name = " ".join(context.args)
    # Default seat limit is 4 for testing (was 35)
    event_id = db.create_event(name, seat_limit=4)
    await update.message.reply_text(f"Event '{name}' created with ID {event_id}. Seat limit: 4")

async def admin_open(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        return

    if update.effective_chat.type != 'private':
        await update.message.reply_text("Please perform admin actions in a private chat.")
        return
    
    events = db.get_events()
    # Filter for closed events
    closed_events = [e for e in events if not e['is_open']]
    
    if not closed_events:
        await update.message.reply_text("No closed events found to open.")
        return
        
    keyboard = []
    for e in closed_events:
        keyboard.append([InlineKeyboardButton(e['name'], callback_data=f"admin_open_{e['id']}")])
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Select an event to OPEN:", reply_markup=reply_markup)

async def admin_close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        return

    if update.effective_chat.type != 'private':
        await update.message.reply_text("Please perform admin actions in a private chat.")
        return
    
    events = db.get_events()
    # Filter for open events
    open_events = [e for e in events if e['is_open']]
    
    if not open_events:
        await update.message.reply_text("No open events found to close.")
        return
        
    keyboard = []
    for e in open_events:
        keyboard.append([InlineKeyboardButton(e['name'], callback_data=f"admin_close_{e['id']}")])
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Select an event to CLOSE:", reply_markup=reply_markup)

async def admin_event_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    action, event_id = data.rsplit('_', 1)
    event_id = int(event_id)
    event = db.get_event(event_id)
    
    if not event:
        await query.edit_message_text("Event not found.")
        return

    if action == 'admin_open':
        db.set_event_open(event_id, True)
        await query.edit_message_text(f"Registration for '{event['name']}' is now OPEN.")
        
    elif action == 'admin_close':
        db.set_event_open(event_id, False)
        await query.edit_message_text(f"Registration for '{event['name']}' CLOSED. Calculating seats...")
        await perform_allocation(update, context, event_id)
        
    elif action == 'admin_list':
        registrations = db.get_event_registrations(event_id)
        if not registrations:
            await query.edit_message_text(f"No registrations found for '{event['name']}'.")
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
        
        msg = f"📋 *Registrations for {event['name']} ({count} seats):*\n\n"
        for reg in registrations:
            icon = "✅" if reg['status'] == 'ACCEPTED' else "⏳" if reg['status'] == 'PENDING' else "❌" if reg['status'] == 'CANCELLED' else "📝"
            safe_name = escape_md(reg['full_name'])
            safe_username = escape_md(reg['username'])
            safe_partner = escape_md(reg['partner_name'])
            
            partner_str = f" (Partner: {safe_partner})" if safe_partner else ""
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
                await context.bot.send_message(chat_id=r['user_id'], text=f"Registration for '{event['name']}' closed. You are on the WAITING list.")
            except Exception as e:
                logging.error(f"Failed to send message to {r['user_id']}: {e}")

    # Notify Accepted
    for uid in accepted_ids:
        try:
            # Find registration to check for partner
            reg = next((r for r in pending if r['user_id'] == uid), None)
            msg = f"Congratulations! You have a seat for '{event['name']}'."
            
            if reg and reg['partner_name']:
                partner_reg = find_partner(reg['partner_name'], pending)
                if not partner_reg:
                    # Partner was not registered, so we inform the user they are both in
                    msg += f"\n\nYour partner ({reg['partner_name']}) is also accepted!"
            
            await context.bot.send_message(chat_id=uid, text=msg)
        except Exception as e:
            logging.error(f"Failed to send message to {uid}: {e}")
            
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Allocation for '{event['name']}' complete. {seats_taken} seats taken.")

async def admin_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        return

    if update.effective_chat.type != 'private':
        await update.message.reply_text("Please perform admin actions in a private chat.")
        return

    events = db.get_events()
    if not events:
        await update.message.reply_text("No events found.")
        return

    keyboard = []
    for e in events:
        keyboard.append([InlineKeyboardButton(e['name'], callback_data=f"admin_list_{e['id']}")])
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Select an event to view registrations:", reply_markup=reply_markup)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and context.args[0] == 'register':
        # Trigger registration flow manually
        # We need to call register(update, context) but return the state
        # However, start is not the entry point of the ConversationHandler in the current setup.
        # We can't easily jump into the ConversationHandler from here without refactoring.
        # Simplest way: Tell them to type /register now that they are here.
        await update.message.reply_text("Welcome! Please type /register to start the registration process.")
        return

    await update.message.reply_text(
        "Welcome to the Event Planner Bot!\n"
        "Use /register to sign up for the event.\n"
        "Use /status to check your registration status.\n"
        "Use /cancel to cancel your registration."
    )

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if update.effective_chat.type != 'private':
        bot_username = context.bot.username
        await update.message.reply_text(f"Please register with me privately: t.me/{bot_username}?start=register")
        return ConversationHandler.END

    events = db.get_events()
    open_events = [e for e in events if e['is_open']]
    
    if not open_events:
        await update.message.reply_text("No events are currently open for registration.")
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
    await update.message.reply_text("Please select an event to register for:", reply_markup=reply_markup)
    return ASK_EVENT

async def event_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    event_id = int(query.data.split('_')[1])
    event = db.get_event(event_id)
    
    if not event or not event['is_open']:
        await query.edit_message_text("This event is no longer open.")
        return ConversationHandler.END
        
    context.user_data['event_id'] = event_id
    context.user_data['event_name'] = event['name']
    
    await query.edit_message_text(f"Selected: {event['name']}")
    return await ask_neuling(update, context)

async def ask_neuling(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    event_id = context.user_data['event_id']
    
    existing = db.get_registration(user.id, event_id)
    if existing:
        msg = "You are already registered for this event."
        if update.callback_query:
            await update.callback_query.message.reply_text(msg)
        else:
            await update.message.reply_text(msg)
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("Yes", callback_data='neuling_yes')],
        [InlineKeyboardButton("No", callback_data='neuling_no')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    msg = "Are you a 'Neuling' (Newbie)?"
    if update.callback_query:
        await update.callback_query.message.reply_text(msg, reply_markup=reply_markup)
    else:
        await update.message.reply_text(msg, reply_markup=reply_markup)
        
    return ASK_NEULING

async def neuling_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    context.user_data['is_neuling'] = (query.data == 'neuling_yes')
    await query.edit_message_text(text=f"Neuling: {'Yes' if context.user_data['is_neuling'] else 'No'}")
    

    
    keyboard = [
        [InlineKeyboardButton("Yes", callback_data='partner_yes')],
        [InlineKeyboardButton("No", callback_data='partner_no')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.reply_text(
        "Do you have a partner?",
        reply_markup=reply_markup
    )
    return ASK_PARTNER_CONFIRM

async def partner_confirm_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    has_partner = (query.data == 'partner_yes')
    
    if has_partner:
        await query.edit_message_text("Do you have a partner? Yes")
        await query.message.reply_text(
            "Please enter their Telegram username (starting with @) or their full name."
        )
        return ASK_PARTNER_NAME
    else:
        await query.edit_message_text("Do you have a partner? No")
        # No partner, proceed to finish registration
        return await finish_registration(update, context, partner_name=None)

async def partner_name_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    partner_name = update.message.text
    
    # Handle commands manually since we are capturing all TEXT
    if partner_name.startswith('/'):
        if partner_name == '/cancel':
            return await cancel(update, context)
        await update.message.reply_text("Please enter a partner name. Do not use commands (except /cancel).")
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
            "✅ *Registration Successful!*\n\n"
            "You have been added to the *PENDING* list.\n"
            "You will be notified once the registration closes and seats are allocated."
        )
        if partner_name:
            msg += f"\n\nPartner registered: {partner_name}\n\n_Note: If your partner wants to receive notifications directly, please ask them to start the bot (@{context.bot.username})._"
            
        if update.callback_query:
             await update.callback_query.message.reply_text(msg, parse_mode='Markdown')
        else:
             await update.message.reply_text(msg, parse_mode='Markdown')
    else:
        if update.callback_query:
             await update.callback_query.message.reply_text("An error occurred during registration.")
        else:
             await update.message.reply_text("An error occurred during registration.")
        
    return ConversationHandler.END

async def notify_next_waiting(context: ContextTypes.DEFAULT_TYPE, event_id):
    waiting_list = db.get_waiting_list(event_id)
    if not waiting_list:
        return

    next_person = waiting_list[0]
    db.update_status(next_person['user_id'], event_id, 'OFFERED')
    
    event = db.get_event(event_id)
    
    keyboard = [
        [InlineKeyboardButton("Accept", callback_data=f'offer_accept_{event_id}')],
        [InlineKeyboardButton("Deny", callback_data=f'offer_deny_{event_id}')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await context.bot.send_message(
            chat_id=next_person['user_id'],
            text=f"A spot has opened up for '{event['name']}'! Do you want to accept it?",
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
        await query.edit_message_text("This offer is no longer valid.")
        return

    if action == 'offer_accept':
        db.update_status(user.id, event_id, 'ACCEPTED')
        await query.edit_message_text("You have accepted the spot! See you there.")
    else:
        db.update_status(user.id, event_id, 'DECLINED')
        await query.edit_message_text("You have declined the spot.")
        # Notify next
        await notify_next_waiting(context, event_id)

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    regs = db.get_user_registrations(user.id)
    if not regs:
        await update.message.reply_text("You are not registered for any events.")
    else:
        msg = "*Your Registrations:*\n"
        for r in regs:
            msg += f"- {r['event_name']}: {r['status']}\n"
        await update.message.reply_text(msg, parse_mode='Markdown')

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    regs = db.get_user_registrations(user.id)
    # Filter for active registrations (not cancelled or declined)
    active_regs = [r for r in regs if r['status'] not in ['CANCELLED', 'DECLINED']]
    
    if not active_regs:
        await update.message.reply_text("You have no active registrations to cancel.")
        return

    if len(active_regs) == 1:
        await perform_cancel(update, context, active_regs[0])
    else:
        keyboard = []
        for r in active_regs:
            keyboard.append([InlineKeyboardButton(r['event_name'], callback_data=f"cancel_{r['event_id']}")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Select an event to cancel registration:", reply_markup=reply_markup)

async def cancel_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    event_id = int(query.data.split('_')[1])
    user = update.effective_user
    reg = db.get_registration(user.id, event_id)
    
    if not reg:
        await query.edit_message_text("Registration not found.")
        return
        
    await perform_cancel(update, context, reg)

async def perform_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE, reg):
    user_id = reg['user_id']
    event_id = reg['event_id']
    
    if reg['status'] == 'CANCELLED':
        msg = "You are already cancelled."
        if update.callback_query:
            await update.callback_query.edit_message_text(msg)
        else:
            await update.message.reply_text(msg)
        return

    was_accepted = (reg['status'] == 'ACCEPTED')
    db.update_status(user_id, event_id, 'CANCELLED')
    
    msg = "Registration cancelled."
    if update.callback_query:
        await update.callback_query.edit_message_text(msg)
    else:
        await update.message.reply_text(msg)
    
    if was_accepted:
        await notify_next_waiting(context, event_id)

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Registration cancelled.")
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
