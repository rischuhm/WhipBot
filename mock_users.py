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
        elif message_text:
            self.message = MockMessage(user, chat, message_text)
        
        self._effective_user = user
        self._effective_chat = chat
    
    @property
    def effective_user(self):
        return self._effective_user
    
    @property
    def effective_chat(self):
        return self._effective_chat


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
        # Set the current user in context if it supports it
        if hasattr(context, 'set_user'):
            context.set_user(mock_user.user_id)
        
        # Clear user_data for this user
        if hasattr(context, 'user_data') and context.user_data is not None:
            context.user_data.clear()
        else:
            # Fallback: create a simple dict
            if not hasattr(context, '_user_data'):
                context._user_data = {}
            context.user_data = context._user_data
        
        # Step 1: Start registration with /register command
        update = MockUpdate(mock_user, message_text="/register")
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
            update = MockUpdate(mock_user, callback_data=f"event_{selected_event['id']}")
            result = await event_response(update, context)
        elif result == ConversationHandler.END:
            # No open events or registration failed
            logger.error(f"Registration ended early for mock user {mock_user.user_id} (no open events?)")
            return False
        elif result == ASK_NEULING:
            # Single event - already selected, verify event_id if provided
            if event_id and context.user_data.get('event_id') != event_id:
                logger.error(f"Event mismatch for mock user {mock_user.user_id}: expected {event_id}, got {context.user_data.get('event_id')}")
                return False
        
        # Step 2: Answer neuling question
        if result == ASK_NEULING:
            callback_data = 'neuling_yes' if mock_user.is_neuling else 'neuling_no'
            update = MockUpdate(mock_user, callback_data=callback_data)
            result = await neuling_response(update, context)
        
        # Step 3: Answer partner question
        if result == ASK_PARTNER_CONFIRM:
            has_partner = mock_user.partner_name is not None
            callback_data = 'partner_yes' if has_partner else 'partner_no'
            update = MockUpdate(mock_user, callback_data=callback_data)
            result = await partner_confirm_response(update, context)
        
        # Step 4: Provide partner name if needed
        if result == ASK_PARTNER_NAME:
            update = MockUpdate(mock_user, message_text=mock_user.partner_name or "")
            result = await partner_name_response(update, context)
        
        # Step 5: Finish registration
        if result == ConversationHandler.END:
            # Check if registration was successful
            event_id_used = context.user_data.get('event_id')
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
    results = {
        'success': 0,
        'failed': 0,
        'details': []
    }
    
    for i in range(count):
        mock_user = MockUser.create_random(i, neuling_probability, partner_probability)
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

