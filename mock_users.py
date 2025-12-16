import random
import logging
from typing import Optional
from telegram.ext import ContextTypes
from telegram.ext import ConversationHandler
import database as db

logger = logging.getLogger(__name__)

# Mock user ID counter - starts at 1000000 to avoid conflicts with real users
_MOCK_USER_ID_COUNTER = 1000000

# Realistic first names
_FIRST_NAMES = [
    "Max", "Anna", "Tom", "Lisa", "Felix", "Sarah", "Lukas", "Julia", "Jonas", "Emma",
    "Ben", "Sophie", "Noah", "Hannah", "Finn", "Mia", "Leon", "Emily", "Paul", "Laura",
    "Luca", "Marie", "Emil", "Lea", "Anton", "Clara", "Theo", "Lena", "Elias", "Amelie",
    "Henry", "Mila", "Oskar", "Luisa", "Jakob", "Charlotte", "Matteo", "Lina", "David", "Nora",
    "Samuel", "Ella", "Alexander", "Maya", "Benjamin", "Ida", "Julian", "Greta", "Liam", "Amelia"
]

# Realistic last names
_LAST_NAMES = [
    "Müller", "Schmidt", "Schneider", "Fischer", "Weber", "Meyer", "Wagner", "Becker", "Schulz", "Hoffmann",
    "Schäfer", "Koch", "Bauer", "Richter", "Klein", "Wolf", "Schröder", "Neumann", "Schwarz", "Zimmermann",
    "Braun", "Krüger", "Hofmann", "Hartmann", "Lange", "Schmitt", "Werner", "Schmitz", "Krause", "Meier",
    "Lehmann", "Schmid", "Schulze", "Maier", "Köhler", "Herrmann", "König", "Walter", "Mayer", "Huber",
    "Kaiser", "Fuchs", "Peters", "Lang", "Scholz", "Möller", "Weiß", "Jung", "Hahn", "Schubert"
]

class MockUser:
    """Represents a mock user for testing."""
    
    def __init__(self, user_id: int, username: str, full_name: str, 
                 is_neuling: bool = False, partner_name: Optional[str] = None):
        self.user_id = user_id
        self.username = username
        self.full_name = full_name
        self.is_neuling = is_neuling
        self.partner_name = partner_name
    
    @classmethod
    def create_random(cls, index: int, neuling_probability: float = 0.3, 
                     partner_probability: float = 0.4):
        """Create a random mock user with realistic name."""
        global _MOCK_USER_ID_COUNTER
        user_id = _MOCK_USER_ID_COUNTER + index
        
        # Generate realistic name
        first_name = random.choice(_FIRST_NAMES)
        last_name = random.choice(_LAST_NAMES)
        full_name = f"{first_name} {last_name}"
        username = f"{first_name.lower()}_{last_name.lower()}_{index}"
        
        is_neuling = random.random() < neuling_probability
        partner_name = None
        if random.random() < partner_probability:
            # Generate realistic partner name
            partner_first = random.choice(_FIRST_NAMES)
            partner_last = random.choice(_LAST_NAMES)
            # Sometimes use same last name (couple), sometimes different
            if random.random() < 0.5:
                partner_name = f"{partner_first} {last_name}"  # Same last name
            else:
                partner_name = f"{partner_first} {partner_last}"  # Different last name
        
        return cls(user_id, username, full_name, is_neuling, partner_name)


class MockUserObj:
    """Simple mock User object."""
    def __init__(self, mock_user: MockUser):
        self.id = mock_user.user_id
        self.username = mock_user.username
        self.is_bot = False
        parts = mock_user.full_name.split() if mock_user.full_name else ["Mock"]
        self.first_name = parts[0]
        self.last_name = " ".join(parts[1:]) if len(parts) > 1 else None
        self.full_name = mock_user.full_name

class MockChat:
    """Simple mock Chat object."""
    def __init__(self, user_id: int):
        self.id = user_id
        self.type = 'private'

class MockMessage:
    """Simple mock Message object."""
    def __init__(self, user: MockUserObj, chat: MockChat, text: str):
        self.message_id = 1
        self.from_user = user
        self.chat = chat
        self.text = text
        self._reply_text_called = False
    
    async def reply_text(self, text: str, **kwargs):
        """Mock reply_text method."""
        logger.debug(f"Mock reply to {self.from_user.id}: {text}")
        self._reply_text_called = True
        return None

class MockCallbackQuery:
    """Simple mock CallbackQuery object."""
    def __init__(self, user: MockUserObj, chat: MockChat, data: str):
        self.id = "mock_callback"
        self.from_user = user
        self.data = data
        self.chat_instance = "mock"
        self.message = MockMessage(user, chat, "")
        self._answer_called = False
        self._edit_called = False
    
    async def answer(self, **kwargs):
        """Mock answer method."""
        logger.debug(f"Mock callback answered for {self.from_user.id}")
        self._answer_called = True
        return None
    
    async def edit_message_text(self, text: str, **kwargs):
        """Mock edit_message_text method."""
        logger.debug(f"Mock edit for {self.from_user.id}: {text}")
        self._edit_called = True
        return None

class MockUpdate:
    """Mock Update object for simulating bot interactions."""
    
    def __init__(self, mock_user: MockUser, message_text: Optional[str] = None, 
                 callback_data: Optional[str] = None):
        self.mock_user = mock_user
        
        # Create mock objects
        user = MockUserObj(mock_user)
        chat = MockChat(mock_user.user_id)
        
        self.message = None
        self.callback_query = None
        
        if callback_data:
            self.callback_query = MockCallbackQuery(user, chat, callback_data)
            self.message = self.callback_query.message
        elif message_text is not None:
            # Use 'is not None' instead of truthiness check to handle empty strings
            self.message = MockMessage(user, chat, message_text)
        
        self._effective_user = user
        self._effective_chat = chat
    
    @property
    def effective_user(self):
        return self._effective_user
    
    @property
    def effective_chat(self):
        return self._effective_chat


def _ensure_user_data_initialized(context: ContextTypes.DEFAULT_TYPE, mock_user: MockUser):
    """
    Ensure that context._user_data has an entry for the mock user before calling handlers.
    This ensures that when handlers access context.user_data, they get the correct user's data.
    
    Args:
        context: The bot context
        mock_user: The mock user whose data should be initialized
    """
    if hasattr(context, '_user_data') and isinstance(context._user_data, dict):
        if mock_user.user_id not in context._user_data:
            context._user_data[mock_user.user_id] = {}
    elif hasattr(context, 'set_user'):
        # For custom mock contexts (like in test scripts), use set_user method
        context.set_user(mock_user.user_id)


def _get_mock_user_data(context: ContextTypes.DEFAULT_TYPE, mock_user: MockUser) -> dict:
    """
    Get user_data for a specific mock user, ensuring we access the correct user's data
    even when context was created with a different user (e.g., admin).
    
    Args:
        context: The bot context
        mock_user: The mock user whose data we want to access
    
    Returns:
        Dictionary containing the mock user's user_data
    """
    # Try to access internal _user_data dict directly by user_id
    if hasattr(context, '_user_data') and isinstance(context._user_data, dict):
        return context._user_data.get(mock_user.user_id, {})
    elif hasattr(context, 'set_user'):
        # For custom mock contexts (like in test scripts), use set_user method
        context.set_user(mock_user.user_id)
        return context.user_data if hasattr(context, 'user_data') else {}
    else:
        # Fallback: try to get via property (may return wrong user's data)
        # This is less reliable but better than nothing
        return context.user_data if hasattr(context, 'user_data') else {}


async def simulate_registration(mock_user: MockUser, context: ContextTypes.DEFAULT_TYPE,
                               event_id: Optional[int] = None) -> bool:
    """
    Simulate the complete registration flow for a mock user.
    
    Args:
        mock_user: The mock user to register
        event_id: Optional event ID. If None, will use the only open event
        context: The bot context
    
    Returns:
        True if registration was successful, False otherwise
    """
    try:
        # Import handlers to avoid circular imports
        from main import register, event_response, neuling_response, partner_confirm_response, partner_name_response, ASK_EVENT, ASK_NEULING, ASK_PARTNER_CONFIRM, ASK_PARTNER_NAME
        
        # Verify event_id if provided
        if event_id:
            event = db.get_event(event_id)
            if not event or not event['is_open']:
                logger.error(f"Event {event_id} not found or not open for mock user {mock_user.user_id}")
                return False
        
        # Initialize user data for this mock user
        # IMPORTANT: When reusing the same context object for multiple mock users,
        # we must explicitly clear the user_data for each mock user to prevent data
        # from one user corrupting another user's registration flow.
        # 
        # The issue: In python-telegram-bot, context.user_data is a property that
        # returns data keyed by update.effective_user.id. However, when we access
        # context.user_data directly in our code (not in a handler), it may use
        # the context's original user ID (e.g., the admin), not the mock user's ID.
        # 
        # Solution: We need to explicitly clear user_data for the mock user's ID.
        # Since context.user_data internally uses a dict keyed by user_id, we can
        # access and clear the mock user's data by temporarily setting the context's
        # effective_user, or by directly accessing the internal storage.
        # 
        # The safest approach: Clear user_data right before calling handlers,
        # ensuring each mock user starts with a clean state. We'll do this by
        # accessing the user_data that handlers will use (based on update.effective_user.id).
        
        # Step 1: Start registration with /register command
        update = MockUpdate(mock_user, message_text="/register")
        
        # CRITICAL: Ensure context.user_data property correctly resolves to mock user's data
        # In python-telegram-bot, context.user_data is a property that should resolve based on
        # update.effective_user.id. However, when reusing a context created for a different user
        # (e.g., admin), we must ensure the internal _user_data dict is properly initialized
        # and cleared for each mock user.
        # 
        # The handlers access context.user_data, which internally uses context._user_data[user_id].
        # We need to ensure that when handlers are called with our MockUpdate, they get the
        # correct user_data dict for the mock user's ID.
        # 
        # Solution: Initialize and clear the mock user's data dict in context._user_data
        # before calling handlers. The handlers should then correctly resolve user_data based
        # on update.effective_user.id, but we ensure the dict exists and is clean.
        _ensure_user_data_initialized(context, mock_user)
        
        # Clear any existing data for this mock user to ensure clean state
        if hasattr(context, '_user_data') and isinstance(context._user_data, dict):
            if mock_user.user_id in context._user_data:
                context._user_data[mock_user.user_id].clear()
        
        result = await register(update, context)
        
        # Check if we need to select an event
        if result == ASK_EVENT:
            # Multiple events - need to select one
            events = db.get_events()
            open_events = [e for e in events if e['is_open']]
            
            if not open_events:
                logger.error(f"No open events for mock user {mock_user.user_id}")
                return False
            
            # Use provided event_id or pick first open event
            if event_id:
                selected_event = next((e for e in open_events if e['id'] == event_id), None)
                if not selected_event:
                    logger.error(f"Event {event_id} not found in open events for mock user {mock_user.user_id}")
                    return False
            else:
                selected_event = open_events[0]
            
            # Simulate event selection callback
            _ensure_user_data_initialized(context, mock_user)
            
            update = MockUpdate(mock_user, callback_data=f"event_{selected_event['id']}")
            result = await event_response(update, context)
        elif result == ConversationHandler.END:
            # No open events or registration failed
            logger.error(f"Registration ended early for mock user {mock_user.user_id} (no open events?)")
            return False
        elif result == ASK_NEULING:
            # Single event - already selected, verify event_id if provided
            # Access user_data directly by user_id to avoid getting admin's data
            mock_user_data = _get_mock_user_data(context, mock_user)
            if event_id and mock_user_data.get('event_id') != event_id:
                logger.error(f"Event mismatch for mock user {mock_user.user_id}: expected {event_id}, got {mock_user_data.get('event_id')}")
                return False
        
        # Step 2: Answer neuling question
        if result == ASK_NEULING:
            _ensure_user_data_initialized(context, mock_user)
            
            callback_data = 'neuling_yes' if mock_user.is_neuling else 'neuling_no'
            update = MockUpdate(mock_user, callback_data=callback_data)
            result = await neuling_response(update, context)
        
        # Step 3: Answer partner question
        if result == ASK_PARTNER_CONFIRM:
            _ensure_user_data_initialized(context, mock_user)
            
            has_partner = mock_user.partner_name is not None
            callback_data = 'partner_yes' if has_partner else 'partner_no'
            update = MockUpdate(mock_user, callback_data=callback_data)
            result = await partner_confirm_response(update, context)
        
        # Step 4: Provide partner name if needed
        if result == ASK_PARTNER_NAME:
            _ensure_user_data_initialized(context, mock_user)
            
            update = MockUpdate(mock_user, message_text=mock_user.partner_name or "")
            result = await partner_name_response(update, context)
        
        # Step 5: Finish registration
        if result == ConversationHandler.END:
            # Check if registration was successful
            # Access user_data directly by user_id to avoid getting admin's data
            mock_user_data = _get_mock_user_data(context, mock_user)
            event_id_used = mock_user_data.get('event_id')
            if event_id_used:
                reg = db.get_registration(mock_user.user_id, event_id_used)
                if reg:
                    logger.info(f"Mock user {mock_user.user_id} ({mock_user.full_name}) registered successfully")
                    return True
        
        logger.warning(f"Mock user {mock_user.user_id} registration did not complete properly (result: {result})")
        return False
        
    except Exception as e:
        logger.error(f"Error simulating registration for mock user {mock_user.user_id}: {e}", exc_info=True)
        return False


async def create_mock_users(count: int, context: ContextTypes.DEFAULT_TYPE,
                           event_id: Optional[int] = None,
                           neuling_probability: float = 0.3,
                           partner_probability: float = 0.4) -> dict:
    """
    Create and register a batch of mock users.
    
    Args:
        count: Number of mock users to create
        event_id: Optional event ID to register for
        neuling_probability: Probability that a mock user is a neuling (0.0-1.0)
        partner_probability: Probability that a mock user has a partner (0.0-1.0)
        context: The bot context
    
    Returns:
        Dictionary with success count, failure count, and details
    """
    # Find the highest existing mock user ID to avoid duplicates
    # IMPORTANT: Always check ALL events, regardless of event_id parameter.
    # The event_id parameter only determines which event to register new users for,
    # not which events to search for existing mock user IDs. This prevents duplicate
    # IDs when mock users exist in different events.
    all_regs = []
    all_events = db.get_events()
    for event in all_events:
        regs = db.get_event_registrations(event['id'])
        all_regs.extend(regs)
    
    max_mock_id = _MOCK_USER_ID_COUNTER - 1  # Start from base - 1
    for reg in all_regs:
        if reg['user_id'] >= _MOCK_USER_ID_COUNTER:
            max_mock_id = max(max_mock_id, reg['user_id'])
    
    # Calculate starting index (how many mock users already exist)
    start_index = max_mock_id - _MOCK_USER_ID_COUNTER + 1
    
    results = {
        'success': 0,
        'failed': 0,
        'details': []
    }
    
    for i in range(count):
        # Use start_index + i to ensure unique IDs across multiple calls
        mock_user = MockUser.create_random(start_index + i, neuling_probability, partner_probability)
        success = await simulate_registration(mock_user, context, event_id)
        
        if success:
            results['success'] += 1
        else:
            results['failed'] += 1
        
        results['details'].append({
            'user_id': mock_user.user_id,
            'username': mock_user.username,
            'full_name': mock_user.full_name,
            'is_neuling': mock_user.is_neuling,
            'partner_name': mock_user.partner_name,
            'success': success
        })
    
    return results

