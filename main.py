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
ASK_NEULING, ASK_PARTNER = range(2)

def find_partner(partner_name, all_registrations):
    if not partner_name:
        return None
    partner_name = partner_name.lower().strip()
    for reg in all_registrations:
        if reg['full_name'].lower().strip() == partner_name:
            return reg
        if reg['username'] and reg['username'].lower().strip() == partner_name:
            return reg
    return None

async def admin_open(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        return
    
    db.set_registration_open(True)
    await update.message.reply_text("Registration is now OPEN.")

async def admin_close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        return
    
    if not db.is_registration_open():
        await update.message.reply_text("Registration is already closed.")
        return

    db.set_registration_open(False)
    await update.message.reply_text("Registration CLOSED. Calculating seats...")
    
    # Allocation Logic
    all_regs = db.get_pending_registrations()
    # Convert to list of dicts for easier handling
    pending = [dict(r) for r in all_regs]
    
    accepted_ids = set()
    seats_limit = 35
    seats_taken = 0
    
    def accept(reg):
        nonlocal seats_taken
        if reg['user_id'] in accepted_ids:
            return
        accepted_ids.add(reg['user_id'])
        seats_taken += 1
        db.update_status(reg['user_id'], 'ACCEPTED')
    
    # 1. Admins
    admins = [r for r in pending if r['is_admin']]
    for r in admins:
        accept(r)
        partner = find_partner(r['partner_name'], pending)
        if partner:
            accept(partner)
            
    # 2. Neulings
    neulings = [r for r in pending if r['is_neuling'] and r['user_id'] not in accepted_ids]
    for r in neulings:
        accept(r)
        partner = find_partner(r['partner_name'], pending)
        if partner:
            accept(partner)
            
    # 3. Random
    remaining = [r for r in pending if r['user_id'] not in accepted_ids]
    random.shuffle(remaining)
    
    for r in remaining:
        if seats_taken >= seats_limit:
            break
        
        if r['user_id'] in accepted_ids:
            continue
            
        partner = find_partner(r['partner_name'], pending)
        
        if partner and partner['user_id'] not in accepted_ids:
            # Check if both fit
            if seats_taken + 2 <= seats_limit:
                accept(r)
                accept(partner)
            else:
                # Skip both if they don't fit? 
                # Or accept one? User says "partner is also chosen". 
                # Implies all or nothing. We skip to waiting list.
                continue
        else:
            if seats_taken + 1 <= seats_limit:
                accept(r)
    
    # 4. Waiting List
    for r in pending:
        if r['user_id'] not in accepted_ids:
            db.update_status(r['user_id'], 'WAITING')
            try:
                await context.bot.send_message(chat_id=r['user_id'], text="Registration closed. You are on the WAITING list.")
            except Exception as e:
                logging.error(f"Failed to send message to {r['user_id']}: {e}")

    # Notify Accepted
    for uid in accepted_ids:
        try:
            await context.bot.send_message(chat_id=uid, text="Congratulations! You have a seat for the event.")
        except Exception as e:
            logging.error(f"Failed to send message to {uid}: {e}")
            
    await update.message.reply_text(f"Allocation complete. {seats_taken} seats taken.")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome to the Event Planner Bot!\n"
        "Use /register to sign up for the event.\n"
        "Use /status to check your registration status.\n"
        "Use /cancel to cancel your registration."
    )

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not db.is_registration_open():
        await update.message.reply_text("Registration is currently closed.")
        return ConversationHandler.END
    
    existing = db.get_registration(user.id)
    if existing:
        await update.message.reply_text("You are already registered.")
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("Yes", callback_data='neuling_yes')],
        [InlineKeyboardButton("No", callback_data='neuling_no')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Are you a 'Neuling' (Newbie)?", reply_markup=reply_markup)
    return ASK_NEULING

async def neuling_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    context.user_data['is_neuling'] = (query.data == 'neuling_yes')
    await query.edit_message_text(text=f"Neuling: {'Yes' if context.user_data['is_neuling'] else 'No'}")
    
    await query.message.reply_text("Do you have a partner? Please enter their name, or type 'No' if you are alone.")
    return ASK_PARTNER

async def partner_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    partner_name = update.message.text
    if partner_name.lower() in ['no', 'none', 'n/a', '-']:
        partner_name = None
    
    user = update.effective_user
    is_neuling = context.user_data.get('is_neuling', False)
    
    # Save to DB
    success = db.add_registration(user.id, user.username, user.full_name, is_neuling, partner_name)
    
    if success:
        # Check if user is admin
        if user.id in ADMIN_IDS:
            db.set_admin(user.id, True)
            
        await update.message.reply_text("Registration successful! You are currently on the PENDING list.")
    else:
        await update.message.reply_text("An error occurred during registration.")
        
    return ConversationHandler.END

async def notify_next_waiting(context: ContextTypes.DEFAULT_TYPE):
    waiting_list = db.get_waiting_list()
    if not waiting_list:
        return

    next_person = waiting_list[0]
    db.update_status(next_person['user_id'], 'OFFERED')
    
    keyboard = [
        [InlineKeyboardButton("Accept", callback_data='offer_accept')],
        [InlineKeyboardButton("Deny", callback_data='offer_deny')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await context.bot.send_message(
            chat_id=next_person['user_id'],
            text="A spot has opened up for the event! Do you want to accept it?",
            reply_markup=reply_markup
        )
    except Exception as e:
        logging.error(f"Failed to notify {next_person['user_id']}: {e}")
        # If we can't reach them, maybe skip? For now, just log.

async def offer_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    reg = db.get_registration(user.id)
    
    if not reg or reg['status'] != 'OFFERED':
        await query.edit_message_text("This offer is no longer valid.")
        return

    if query.data == 'offer_accept':
        db.update_status(user.id, 'ACCEPTED')
        await query.edit_message_text("You have accepted the spot! See you there.")
    else:
        db.update_status(user.id, 'DECLINED')
        await query.edit_message_text("You have declined the spot.")
        # Notify next
        await notify_next_waiting(context)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    reg = db.get_registration(user.id)
    if not reg:
        await update.message.reply_text("You are not registered.")
        return

    if reg['status'] == 'CANCELLED':
        await update.message.reply_text("You are already cancelled.")
        return

    was_accepted = (reg['status'] == 'ACCEPTED')
    db.update_status(user.id, 'CANCELLED')
    await update.message.reply_text("Registration cancelled.")
    
    if was_accepted:
        await notify_next_waiting(context)

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    reg = db.get_registration(user.id)
    if not reg:
        await update.message.reply_text("You are not registered.")
    else:
        await update.message.reply_text(f"Your status: {reg['status']}")

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
            ASK_NEULING: [CallbackQueryHandler(neuling_response)],
            ASK_PARTNER: [MessageHandler(filters.TEXT & ~filters.COMMAND, partner_response)]
        },
        fallbacks=[CommandHandler('cancel', cancel_conversation)]
    )
    
    application.add_handler(CommandHandler('start', start))
    application.add_handler(reg_handler)
    application.add_handler(CommandHandler('cancel', cancel))
    application.add_handler(CommandHandler('status', status))
    application.add_handler(CommandHandler('admin_open', admin_open))
    application.add_handler(CommandHandler('admin_close', admin_close))
    application.add_handler(CallbackQueryHandler(offer_response, pattern='^offer_'))
    
    print("Bot is running...")
    application.run_polling()
