import os
import logging
from datetime import datetime
from urllib.parse import urlparse
import uuid # For generating unique IDs

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters,
    ConversationHandler
)

# --- 1. Configure Logging ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- 2. Bot Configuration (IMPORTANT: USE ENVIRONMENT VARIABLES FOR SECURITY!) ---
# Replace with your actual token from BotFather or set as environment variable
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "7397962208:AAHmGjRLUsf27qrhdVeScChtYJWFCjw94g8")

# Admin Passwords (Highly recommend setting these as environment variables in production!)
ADMIN_MASTER_PASSWORD = os.getenv("ADMIN_MASTER_PASSWORD", "ADMIN47")
EDIT_LINK_PASSWORD = os.getenv("EDIT_LINK_PASSWORD", "ADMIN9292")
DELETE_LINK_PASSWORD = os.getenv("DELETE_LINK_PASSWORD", "ADMIN4420")

# Default SVG icon from your HTML for links without valid icons
DEFAULT_SVG_ICON = 'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCI+PHBhdGggZmlsbD0iIzkwYjBjOCIgZD0iTTEyLDIyQzYuNDgsMjIsMiwxNy41MiwyLDEyUzYuNDgsMiwxMiwyczEwLDQuNDgsMTAsMTBTSDE3LjUyLDIyLDEyLDIyLzBNMjQsMThjLTQuNDEsMC04LTMuNTktOC04czMuNTktOCw4LTggOCwzLjU5LDgsOFMxOS41OSwyMCwyNCwxOHoiLz48L2Vncz4='

# --- 3. In-Memory Data Storage (WARNING: Data will be lost on bot restart!) ---
all_airdrops_in_memory = []
# You can pre-populate this list with some default airdrops if you wish:
# all_airdrops_in_memory = [
#     {
#         'id': '1',
#         'title': 'Example Airdrop 1',
#         'url': 'https://example.com/airdrop1',
#         'icon': '',
#         'description': 'This is a sample airdrop for testing.',
#         'referral': 'SAMPLECODE1',
#         'timestamp': int(datetime.now().timestamp() * 1000)
#     },
#     {
#         'id': '2',
#         'title': 'Another Airdrop',
#         'url': 'https://anotherexample.com/airdrop',
#         'icon': '',
#         'description': 'Participate to earn tokens!',
#         'referral': 'ANOTHERREF',
#         'timestamp': int(datetime.now().timestamp() * 1000) - 3600000 # 1 hour ago
#     }
# ]
current_id_counter = 0 # Simple counter for new airdrop IDs. More robust would be UUID.
if all_airdrops_in_memory:
    # Set counter based on existing IDs to avoid conflicts if pre-populated
    try:
        max_id = max([int(link['id']) for link in all_airdrops_in_memory if link['id'].isdigit()])
        current_id_counter = max_id + 1
    except ValueError: # If IDs are not purely numeric
        current_id_counter = 1 # Start from 1 if mixed or non-numeric IDs
else:
    current_id_counter = 1


# --- 4. Conversation States for Add/Edit/Delete Operations ---
# Used by ConversationHandler to manage multi-step user input
TITLE, URL, ICON, DESCRIPTION, REFERRAL = range(5)
ADMIN_LOGIN_PASS = range(5, 6)
EDIT_ID_PROMPT, EDIT_PASS_PROMPT, EDIT_FIELD_SELECT, EDIT_NEW_VALUE = range(6, 10)
DELETE_ID_PROMPT, DELETE_PASS_PROMPT, DELETE_CONFIRMATION = range(10, 13)


# --- 5. In-Memory Admin Authentication ---
# Stores chat_ids of authenticated admins for the current bot session.
# This is NOT persistent across bot restarts.
authenticated_admins = set()

def is_admin(user_id):
    """Checks if a user is currently authenticated as an admin."""
    return user_id in authenticated_admins

# --- 6. Utility Functions for Data Handling ---
def sanitize_link_data(link_data, link_id=None):
    """
    Cleans and standardizes link data, applying default icon logic.
    Mimics the JavaScript `sanitizeLink` function.
    """
    title = str(link_data.get('title', 'Untitled Link')).strip()
    url = str(link_data.get('url', '#')).strip()
    icon = str(link_data.get('icon', '')).strip()
    description = str(link_data.get('description', '')).strip()
    referral = str(link_data.get('referral', '')).strip()
    # Ensure timestamp is milliseconds
    timestamp = link_data.get('timestamp') 
    if not isinstance(timestamp, (int, float)):
        timestamp = int(datetime.now().timestamp() * 1000)

    # Icon URL logic: If empty or invalid, try to get favicon, else use default SVG
    if not icon:
        try:
            parsed_url = urlparse(url)
            domain = parsed_url.hostname
            if domain:
                icon = f"https://www.google.com/s2/favicons?domain={domain}&sz=128"
            else:
                icon = DEFAULT_SVG_ICON
        except Exception:
            icon = DEFAULT_SVG_ICON
    else:
        try:
            # Ensure the provided icon URL is valid
            parsed_icon_url = urlparse(icon)
            if not all([parsed_icon_url.scheme, parsed_icon_url.netloc]):
                icon = DEFAULT_SVG_ICON # Fallback if provided icon URL is invalid
        except ValueError:
            icon = DEFAULT_SVG_ICON # Fallback if provided icon URL is invalid
    
    # Construct the final sanitized dictionary
    sanitized_link = {
        'title': title,
        'url': url,
        'icon': icon,
        'description': description,
        'referral': referral,
        'timestamp': timestamp,
        'id': link_id if link_id else str(uuid.uuid4()) # Use UUID for ID if not provided
    }
    
    return sanitized_link

def get_all_links_from_memory():
    """Retrieves all links from in-memory storage, sorted by timestamp."""
    # Ensure data is sorted by timestamp (most recent first)
    return sorted(all_airdrops_in_memory, key=lambda x: x.get('timestamp', 0), reverse=True)

def find_link_by_id(link_id):
    """Helper to find a link by its ID in the in-memory list."""
    for link in all_airdrops_in_memory:
        if link.get('id') == link_id:
            return link
    return None

def format_timestamp(ms_timestamp):
    """Formats a millisecond timestamp to a human-readable string."""
    if not ms_timestamp or not isinstance(ms_timestamp, (int, float)):
        return 'N/A'
    dt_object = datetime.fromtimestamp(ms_timestamp / 1000)
    return dt_object.strftime('%Y-%m-%d %H:%M')

# --- 7. Basic Bot Commands ---

async def start(update: Update, context):
    """Sends a welcome message and basic instructions."""
    await update.message.reply_html(
        "👋 Welcome to the <b>WEB3 Airdrop Portal Bot</b>!\n\n"
        "Here's what you can do:\n"
        "•  /list - See all available airdrops.\n"
        "•  /search <query> - Find airdrops by title, description, or referral code.\n"
        "•  /admin_login - (Admins only) Access management features.\n"
        "•  /admin_logout - (Admins only) Log out from admin session.\n\n"
        "<b>⚠️ Note: This bot's data is stored in memory and will be lost on restart.</b>\n"
        "Feel free to explore!"
    )

async def list_airdrops(update: Update, context):
    """Lists all airdrops with inline buttons for details."""
    links = get_all_links_from_memory()
    if not links:
        await update.message.reply_html("No airdrops found yet. Use /add_airdrop (as admin) to add some!")
        return

    message = "<b>🚀 Current Airdrops:</b>\n\n"
    keyboard_buttons = []
    for i, link in enumerate(links):
        message += f"{i+1}. <b>{link['title']}</b>\n"
        keyboard_buttons.append([InlineKeyboardButton(f"View Details: {link['title']}", callback_data=f"details_{link['id']}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard_buttons)
    await update.message.reply_html(message, reply_markup=reply_markup)

async def search_airdrops(update: Update, context):
    """Searches airdrops based on a user-provided query."""
    query_text = " ".join(context.args).lower().strip()
    if not query_text:
        await update.message.reply_text("Please provide a search query. Usage: `/search <query>` (e.g., `/search defi`)")
        return

    all_links = get_all_links_from_memory()
    results = [
        link for link in all_links
        if query_text in link['title'].lower() or
           query_text in link['description'].lower() or
           query_text in link['referral'].lower()
    ]

    if not results:
        await update.message.reply_html(f"No airdrops found matching '<i>{query_text}</i>'.")
        return

    message = f"<b>🔎 Search Results for '<i>{query_text}</i>':</b>\n\n"
    keyboard_buttons = []
    for i, link in enumerate(results):
        message += f"{i+1}. <b>{link['title']}</b>\n"
        keyboard_buttons.append([InlineKeyboardButton(f"View Details: {link['title']}", callback_data=f"details_{link['id']}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard_buttons)
    await update.message.reply_html(message, reply_markup=reply_markup)

# --- 8. Callback Query Handlers (for Inline Buttons) ---

async def handle_details_callback(update: Update, context):
    """Displays detailed information for a selected airdrop."""
    query = update.callback_query
    await query.answer() # Acknowledge the callback query to remove "loading" state on button

    link_id = query.data.split('_')[1]
    link = find_link_by_id(link_id)

    if not link:
        await query.edit_message_text("Airdrop not found or might have been deleted.")
        return

    message = (
        f"<b>🚀 {link['title']}</b>\n\n"
        f"<b>Description:</b> {link['description'] or '<i>No description provided.</i>'}\n"
        f"<b>Referral Code:</b> <code>{link['referral'] or '<i>N/A</i>'}</code>\n"
        f"<b>URL:</b> <a href='{link['url']}'>{link['url']}</a>\n\n"
        f"<i>Added/Last Updated: {format_timestamp(link['timestamp'])}</i>\n"
        f"<i>(ID: {link['id']})</i>"
    )

    keyboard = [[
        InlineKeyboardButton("Visit Airdrop", url=link['url'])
    ]]
    # Only add copy button if referral code exists
    if link['referral']:
        keyboard[0].append(InlineKeyboardButton("Copy Referral Code", callback_data=f"copyref_{link['referral']}"))
    
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        message, 
        reply_markup=reply_markup, 
        parse_mode='HTML', 
        disable_web_page_preview=True # Prevent large link previews
    )

async def handle_copy_referral_callback(update: Update, context):
    """Sends the referral code to the user for easy copying."""
    query = update.callback_query
    # Acknowledge the callback, the message will show on the user's side briefly
    await query.answer("Referral code sent! Tap to copy.") 
    
    referral_code = query.data.split('_')[1]
    
    # Send the code wrapped in `<code>` tags for easy copying on Telegram mobile apps
    await query.message.reply_html(
        f"<b>Referral Code:</b>\n<code>{referral_code}</code>\n"
        f"<i>(Tap the code above to copy it to your clipboard.)</i>"
    )

# --- 9. Admin Authentication Conversation ---

async def admin_login_start(update: Update, context):
    """Starts the admin login conversation."""
    if is_admin(update.effective_user.id):
        await update.message.reply_text("You are already logged in as admin.")
        return ConversationHandler.END
    await update.message.reply_html("Please enter the <b>admin master password</b> to gain access to admin features.", parse_mode='HTML')
    return ADMIN_LOGIN_PASS

async def admin_login_verify(update: Update, context):
    """Verifies the entered admin master password."""
    entered_password = update.message.text
    if entered_password == ADMIN_MASTER_PASSWORD:
        authenticated_admins.add(update.effective_user.id)
        await update.message.reply_html("✅ <b>Admin access granted!</b>\n"
                                        "You can now use: /add_airdrop, /edit_airdrop, /delete_airdrop.")
        logger.info(f"Admin {update.effective_user.id} logged in.")
        return ConversationHandler.END
    else:
        await update.message.reply_html("❌ Incorrect password. Please try again or type /cancel to stop.")
        return ADMIN_LOGIN_PASS # Stay in the same state to re-prompt

async def admin_logout(update: Update, context):
    """Logs out an authenticated admin."""
    if update.effective_user.id in authenticated_admins:
        authenticated_admins.remove(update.effective_user.id)
        await update.message.reply_html("You have been logged out as admin. Admin features are now disabled.")
        logger.info(f"Admin {update.effective_user.id} logged out.")
    else:
        await update.message.reply_html("You are not currently logged in as admin.")

# --- 10. Admin: Add Airdrop Conversation ---

async def add_airdrop_start(update: Update, context):
    """Starts the conversation to add a new airdrop."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_html("You need <b>admin access</b> to add airdrops. Please use /admin_login first.")
        return ConversationHandler.END
    
    context.user_data['new_airdrop'] = {} # Initialize a dictionary to store new airdrop data
    await update.message.reply_text("Alright, let's add a new airdrop!\nEnter the <b>Title</b> for the airdrop:", parse_mode='HTML')
    return TITLE

async def add_airdrop_title(update: Update, context):
    context.user_data['new_airdrop']['title'] = update.message.text.strip()
    await update.message.reply_text("Great! Now, enter the <b>URL</b> for the airdrop (e.g., `https://example.com/airdrop`):", parse_mode='HTML')
    return URL

async def add_airdrop_url(update: Update, context):
    url = update.message.text.strip()
    try:
        parsed = urlparse(url)
        if all([parsed.scheme, parsed.netloc]): # Check if it has a scheme (http/https) and network location
            context.user_data['new_airdrop']['url'] = url
            await update.message.reply_text("Optional: Enter the <b>Icon URL</b> (e.g., `https://example.com/logo.png`) or type `skip`:", parse_mode='HTML')
            return ICON
        else:
            await update.message.reply_html("❌ Invalid URL. Please enter a <b>valid URL</b> starting with `http://` or `https://`:")
            return URL
    except ValueError:
        await update.message.reply_html("❌ Invalid URL format. Please enter a <b>valid URL</b>:")
        return URL

async def add_airdrop_icon(update: Update, context):
    icon_url = update.message.text.strip()
    if icon_url.lower() != 'skip':
        try:
            parsed = urlparse(icon_url)
            if not all([parsed.scheme, parsed.netloc]):
                await update.message.reply_html("❌ Invalid Icon URL. Enter a <b>valid Icon URL</b> or type `skip`:")
                return ICON
            context.user_data['new_airdrop']['icon'] = icon_url
        except ValueError:
            await update.message.reply_html("❌ Invalid Icon URL format. Enter a <b>valid Icon URL</b> or type `skip`:")
            return ICON
    else:
        context.user_data['new_airdrop']['icon'] = '' # Store empty string if skipped

    await update.message.reply_text("Optional: Enter a short <b>Description</b> for the airdrop (or type `skip`):", parse_mode='HTML')
    return DESCRIPTION

async def add_airdrop_description(update: Update, context):
    description = update.message.text.strip()
    context.user_data['new_airdrop']['description'] = '' if description.lower() == 'skip' else description
    await update.message.reply_text("Optional: Enter a <b>Referral Code</b> (or type `skip`):", parse_mode='HTML')
    return REFERRAL

async def add_airdrop_referral(update: Update, context):
    referral_code = update.message.text.strip()
    context.user_data['new_airdrop']['referral'] = '' if referral_code.lower() == 'skip' else referral_code
    
    # Generate ID and add to in-memory list
    try:
        global current_id_counter
        new_id = str(current_id_counter)
        current_id_counter += 1 # Increment for next airdrop

        # Sanitize data and explicitly add the generated ID
        link_data_to_save = sanitize_link_data(context.user_data['new_airdrop'], link_id=new_id)
        
        all_airdrops_in_memory.append(link_data_to_save)
        await update.message.reply_html(f"✅ Airdrop '<b>{link_data_to_save['title']}</b>' added successfully!\n"
                                        f"<i>ID: {link_data_to_save['id']}</i>")
        logger.info(f"New airdrop added by {update.effective_user.id}: {link_data_to_save['title']} ({link_data_to_save['id']})")
    except Exception as e:
        logger.error(f"Error adding airdrop to memory: {e}")
        await update.message.reply_html("❌ Failed to add airdrop. Please try again later.")
    
    context.user_data.pop('new_airdrop', None) # Clean up user data
    return ConversationHandler.END

# --- 11. Admin: Edit Airdrop Conversation ---

async def edit_airdrop_start(update: Update, context):
    """Starts the conversation to edit an airdrop."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_html("You need <b>admin access</b> to edit airdrops. Please use /admin_login first.")
        return ConversationHandler.END
    
    await update.message.reply_html("To edit an airdrop, please provide its <b>ID</b> (e.g., `1`, `2`):")
    return EDIT_ID_PROMPT

async def edit_airdrop_id_prompt(update: Update, context):
    link_id = update.message.text.strip()
    link_data = find_link_by_id(link_id)

    if not link_data:
        await update.message.reply_html("❌ Airdrop with that ID not found. Please enter a <b>valid ID</b> or type /cancel.")
        return EDIT_ID_PROMPT
    
    context.user_data['edit_link_id'] = link_id
    context.user_data['original_link_data'] = link_data # Store original data for reference
    
    await update.message.reply_html(f"Found airdrop '<b>{link_data.get('title', 'N/A')}</b>'.\nPlease enter the <b>edit password</b> to proceed:", parse_mode='HTML')
    return EDIT_PASS_PROMPT

async def edit_airdrop_password_verify(update: Update, context):
    """Verifies the edit password."""
    entered_password = update.message.text
    if entered_password != EDIT_LINK_PASSWORD:
        await update.message.reply_html("❌ Incorrect edit password. Please try again or type /cancel.")
        return EDIT_PASS_PROMPT # Stay in this state
    
    link_id = context.user_data['edit_link_id']
    original_data = context.user_data['original_link_data']

    keyboard = [
        [InlineKeyboardButton("Title", callback_data="editfield_title")],
        [InlineKeyboardButton("URL", callback_data="editfield_url")],
        [InlineKeyboardButton("Icon URL", callback_data="editfield_icon")],
        [InlineKeyboardButton("Description", callback_data="editfield_description")],
        [InlineKeyboardButton("Referral Code", callback_data="editfield_referral")],
        [InlineKeyboardButton("Cancel Edit", callback_data="editfield_cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_html(f"✅ Password correct. Which field of '<b>{original_data.get('title', 'N/A')}</b>' would you like to edit?", reply_markup=reply_markup)
    return EDIT_FIELD_SELECT # Move to state where we wait for field selection

async def edit_airdrop_select_field(update: Update, context):
    """Handles the callback for selecting which field to edit."""
    query = update.callback_query
    
    # This function is designed to handle CallbackQuery (button clicks).
    # If a MessageHandler somehow directs here (e.g., if a user types something),
    # update.callback_query will be None, leading to an AttributeError.
    # We ensure it's a callback query before proceeding.
    if not query:
        # This case should ideally not be reached if ConversationHandler states are strict.
        # But if it does, it indicates unexpected text input.
        # Inform the user to use buttons.
        await update.message.reply_html("Please use the inline buttons to select a field, or type /cancel to stop.")
        return EDIT_FIELD_SELECT # Stay in this state to re-prompt for button click.

    await query.answer()

    if query.data == "editfield_cancel":
        await query.edit_message_text("Edit operation cancelled.")
        context.user_data.pop('edit_link_id', None)
        context.user_data.pop('original_link_data', None)
        context.user_data.pop('field_to_edit', None)
        return ConversationHandler.END
    
    field_to_edit = query.data.replace("editfield_", "")
    context.user_data['field_to_edit'] = field_to_edit
    
    await query.edit_message_text(f"Please enter the <b>new value</b> for '<b>{field_to_edit.replace('_', ' ').title()}</b>':\n"
                                  f"<i>(Type `skip` to leave it blank, or `null` to reset if applicable)</i>", parse_mode='HTML')
    return EDIT_NEW_VALUE # Move to state where we wait for the new value

async def edit_airdrop_new_value(update: Update, context):
    """Updates the selected field in the in-memory list with the new value."""
    link_id = context.user_data.get('edit_link_id')
    field = context.user_data.get('field_to_edit')
    new_value = update.message.text.strip()

    if not link_id or not field:
        await update.message.reply_html("❌ Something went wrong with the edit process. Please try /edit_airdrop again.")
        return ConversationHandler.END

    # Handle 'skip' or 'null' input to clear fields
    if new_value.lower() == 'skip' or new_value.lower() == 'null':
        new_value = ''

    try:
        # Find the link in the in-memory list
        link_to_update = find_link_by_id(link_id)
        if not link_to_update:
            await update.message.reply_html("❌ Airdrop not found during update. It might have been deleted by someone else.")
            return ConversationHandler.END

        # Update the specific field
        link_to_update[field] = new_value
        link_to_update['timestamp'] = int(datetime.now().timestamp() * 1000) # Update timestamp on edit

        # Re-sanitize to apply icon logic if URL/icon changed, etc.
        # This will also ensure timestamp is preserved.
        updated_sanitized_link = sanitize_link_data(link_to_update, link_id)
        
        # Replace the old version of the link in the list with the updated one
        for i, link in enumerate(all_airdrops_in_memory):
            if link.get('id') == link_id:
                all_airdrops_in_memory[i] = updated_sanitized_link
                break

        await update.message.reply_html(f"✅ Airdrop '<b>{updated_sanitized_link.get('title', 'N/A')}</b>' successfully updated '<b>{field.replace('_', ' ').title()}</b>'.")
        logger.info(f"Airdrop {link_id} updated by {update.effective_user.id}: field '{field}' changed to '{new_value}'")
    except Exception as e:
        logger.error(f"Error updating airdrop {link_id} in memory: {e}")
        await update.message.reply_html(f"❌ Failed to update airdrop. Error: {e}. Please try again later.")
    
    # Clean up user data
    context.user_data.pop('edit_link_id', None)
    context.user_data.pop('original_link_data', None)
    context.user_data.pop('field_to_edit', None)
    return ConversationHandler.END

# --- 12. Admin: Delete Airdrop Conversation ---

async def delete_airdrop_start(update: Update, context):
    """Starts the conversation to delete an airdrop."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_html("You need <b>admin access</b> to delete airdrops. Please use /admin_login first.")
        return ConversationHandler.END
    
    await update.message.reply_html("To delete an airdrop, please provide its <b>ID</b>:")
    return DELETE_ID_PROMPT

async def delete_airdrop_id_prompt(update: Update, context):
    link_id = update.message.text.strip()
    link_data = find_link_by_id(link_id)

    if not link_data:
        await update.message.reply_html("❌ Airdrop with that ID not found. Please enter a <b>valid ID</b> or type /cancel.")
        return DELETE_ID_PROMPT
    
    context.user_data['delete_link_id'] = link_id
    context.user_data['delete_link_title'] = link_data.get('title', 'N/A')

    await update.message.reply_html(f"Found airdrop '<b>{link_data.get('title', 'N/A')}</b>'.\nPlease enter the <b>delete password</b> to confirm:", parse_mode='HTML')
    return DELETE_PASS_PROMPT

async def delete_airdrop_password_verify(update: Update, context):
    """Verifies the delete password."""
    entered_password = update.message.text
    if entered_password != DELETE_LINK_PASSWORD:
        await update.message.reply_html("❌ Incorrect delete password. Please try again or type /cancel.")
        return DELETE_PASS_PROMPT # Stay in this state

    link_id = context.user_data.get('delete_link_id')
    link_title = context.user_data.get('delete_link_title')

    keyboard = [[
        InlineKeyboardButton("Yes, Delete Permanently", callback_data=f"confirmdelete_{link_id}"),
        InlineKeyboardButton("No, Cancel", callback_data="canceldelete")
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_html(f"✅ Password correct.\nAre you <b>absolutely sure</b> you want to delete '<b>{link_title}</b>'? This action cannot be undone.", reply_markup=reply_markup)
    return ConversationHandler.END # Conversation ends here, further action by callback

async def delete_airdrop_confirm_callback(update: Update, context):
    """Handles the confirmation callback for deletion."""
    query = update.callback_query
    await query.answer()

    if query.data == "canceldelete":
        await query.edit_message_text("Deletion cancelled.")
        context.user_data.pop('delete_link_id', None)
        context.user_data.pop('delete_link_title', None)
        return

    link_id = query.data.replace("confirmdelete_", "")
    link_title = context.user_data.get('delete_link_title', 'Airdrop') # Fallback title

    try:
        # Remove the link from the in-memory list
        global all_airdrops_in_memory
        initial_len = len(all_airdrops_in_memory)
        all_airdrops_in_memory = [link for link in all_airdrops_in_memory if link.get('id') != link_id]
        
        if len(all_airdrops_in_memory) < initial_len:
            await query.edit_message_text(f"✅ Airdrop '<b>{link_title}</b>' successfully deleted.")
            logger.info(f"Airdrop {link_id} deleted by {update.effective_user.id}.")
        else:
            await query.edit_message_text(f"❌ Airdrop '<b>{link_title}</b>' not found or already deleted.")
            logger.warning(f"Attempted to delete non-existent airdrop {link_id} by {update.effective_user.id}.")

    except Exception as e:
        logger.error(f"Error deleting airdrop {link_id} from memory: {e}")
        await query.edit_message_text(f"❌ Failed to delete airdrop. Error: {e}. Please try again later.")
    
    context.user_data.pop('delete_link_id', None)
    context.user_data.pop('delete_link_title', None)

# --- 13. Global Error and Cancel Handling ---

async def cancel_conversation(update: Update, context):
    """Cancels any ongoing conversation and clears user data."""
    if update.message:
        await update.message.reply_html("🚫 Operation cancelled. Your data has been cleared for this process.")
    elif update.callback_query: # If cancellation happens via callback query
        await update.callback_query.message.reply_html("🚫 Operation cancelled.")
        await update.callback_query.answer()
    
    context.user_data.clear() # Clear all conversation data for this user
    return ConversationHandler.END

async def error_handler(update: Update, context):
    """Log the error and send a message to the user."""
    logger.warning(f'Update "{update}" caused error "{context.error}"')
    if update.effective_message:
        await update.effective_message.reply_html(
            f"An unexpected error occurred: <code>{context.error}</code>. "
            "Please try again or use /cancel to reset."
        )

# --- 14. Main Bot Setup Function ---
def main():
    """Starts the bot."""
    # Create the Application and pass your bot's token.
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Register Handlers:
    # Basic Commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("list", list_airdrops))
    application.add_handler(CommandHandler("search", search_airdrops))
    application.add_handler(CommandHandler("admin_logout", admin_logout))

    # Callback Query Handlers for inline buttons
    application.add_handler(CallbackQueryHandler(handle_details_callback, pattern=r"^details_"))
    application.add_handler(CallbackQueryHandler(handle_copy_referral_callback, pattern=r"^copyref_"))
    
    # --- Admin Login Conversation Handler ---
    admin_login_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("admin_login", admin_login_start)],
        states={
            ADMIN_LOGIN_PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_login_verify)],
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
        allow_reentry=True # Allows users to restart the conversation
    )
    application.add_handler(admin_login_conv_handler)

    # --- Add Airdrop Conversation Handler ---
    add_airdrop_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("add_airdrop", add_airdrop_start)],
        states={
            TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_airdrop_title)],
            URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_airdrop_url)],
            ICON: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_airdrop_icon)],
            DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_airdrop_description)],
            REFERRAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_airdrop_referral)],
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
        allow_reentry=True
    )
    application.add_handler(add_airdrop_conv_handler)
    
    # --- Edit Airdrop Conversation Handler ---
    edit_airdrop_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("edit_airdrop", edit_airdrop_start)],
        states={
            EDIT_ID_PROMPT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_airdrop_id_prompt)],
            EDIT_PASS_PROMPT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_airdrop_password_verify)],
            EDIT_FIELD_SELECT: [
                # Only allow CallbackQueryHandler (button clicks) for field selection.
                # The original MessageHandler here could cause an AttributeError if user typed instead of clicked,
                # because `edit_airdrop_select_field` expects `update.callback_query`.
                CallbackQueryHandler(edit_airdrop_select_field, pattern=r"^editfield_"),
            ],
            EDIT_NEW_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_airdrop_new_value)],
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
        allow_reentry=True
    )
    application.add_handler(edit_airdrop_conv_handler)

    # --- Delete Airdrop Conversation Handler ---
    delete_airdrop_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("delete_airdrop", delete_airdrop_start)],
        states={
            DELETE_ID_PROMPT: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_airdrop_id_prompt)],
            DELETE_PASS_PROMPT: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_airdrop_password_verify)],
        },
        # Confirmation is handled by a separate CallbackQueryHandler
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
        allow_reentry=True
    )
    application.add_handler(delete_airdrop_conv_handler)

    # Specific callback for delete confirmation (needs to be outside ConversationHandler if it ends the conversation)
    application.add_handler(CallbackQueryHandler(delete_airdrop_confirm_callback, pattern=r"^(confirmdelete_|canceldelete)$"))


    # Register global error handler
    application.add_error_handler(error_handler)

    logger.info("Bot is starting polling...")
    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()