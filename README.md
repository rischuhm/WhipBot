# EventBot

A Telegram bot for managing event registrations with automatic seat allocation. The bot handles event creation, user registration, and intelligent seat allocation based on priority (admins, neulings, then random selection).

## Setup

1.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

2.  **Configuration**:
    -   Copy `.env.example` to `.env`.
    -   Add your `TELEGRAM_TOKEN` (from BotFather).
    -   Add `ADMIN_IDS` (comma-separated list of Telegram User IDs for admins).

3.  **Run**:
    ```bash
    python main.py
    ```
    
    The bot will start polling for updates. You should see "Bot is running..." in the console.

**Note**: Make sure your `.env` file is in the same directory as `main.py` and contains valid `TELEGRAM_TOKEN` and `ADMIN_IDS`.

## Commands

### User Commands

-   `/start`: Welcome message with list of open events and basic instructions.
-   `/register`: Register for an event. The bot will guide you through:
    - Event selection (if multiple events are open)
    - Neuling question (are you new?)
    - Partner question (bringing someone along?)
    - Partner name (if applicable)
-   `/events`: List all events (open and closed) with their current status.
-   `/status`: Check your registration status for all events you've registered for.
-   `/cancel`: Cancel your registration for a specific event. If you were accepted, your spot will be offered to the waiting list.

### Admin Commands

**Note**: All admin commands must be used in a private chat with the bot.

-   `/create_event <name>`: Create a new event with the specified name.
    - Example: `/create_event Stammtisch Dec`
    - Default seat limit: 35 (can be modified in code)
-   `/admin_open`: Open registration for a specific event. Shows a list of closed events to choose from.
-   `/admin_close`: Close registration for a specific event and automatically run the seat allocation algorithm.
    - Shows a list of open events to choose from
    - Allocates seats based on priority (admins → neulings → random)
    - Notifies all users of their status
-   `/admin_list`: View all registrations for a specific event.
    - Shows user names, usernames, status, neuling status, and partner information
    - Displays registration count and seat allocation
-   `/mock_users <count> [event_id] [neuling_prob] [partner_prob]`: Create mock users for testing (see [Testing section](#testing-with-mock-users) below).

## Seat Allocation Logic

When `/admin_close` is run for an event, the bot automatically allocates seats using the following priority system:

1.  **Admins**: Automatically accepted (plus their partner if they have one).
2.  **Neulings**: Automatically accepted (plus their partner if they have one).
3.  **Random Selection**: Remaining seats (up to the event's seat limit, default 35) are filled randomly from the remaining applicants.
    -   Partners are treated as a unit: either both get in, or neither (if only 1 seat remains).
    -   If a user has a partner name but the partner isn't registered separately, the partner still counts as a seat.
4.  **Waiting List**: Everyone else is moved to the waiting list for that event.

**Notification System:**
- Accepted users receive a congratulatory message
- Waiting list users are notified that they're on the waiting list
- If an accepted user cancels, the first person on the waiting list is automatically offered the spot

## Cancellation

Users can cancel their registration using `/cancel`. The system handles cancellations intelligently:

1.  **User cancels**: Their status becomes `CANCELLED`.
2.  **Automatic notification**: If the user was accepted, the first person on the waiting list is automatically notified.
3.  **Offer system**: The waiting list user receives a message with "Accept" / "Deny" buttons.
4.  **Cascade**: If they decline, the next person on the waiting list is offered the spot.

**Note**: Only active registrations (not already cancelled or declined) can be cancelled.

## Testing with Mock Users

The bot includes a mock user testing system that allows you to simulate the complete registration flow for testing purposes.

### Using the `/mock_users` Admin Command

The `/mock_users` command allows you to create and register mock users programmatically:

**Basic Usage:**
```
/mock_users <count> [event_id] [neuling_probability] [partner_probability]
```

**Examples:**
- `/mock_users 10` - Creates 10 mock users for the first open event
- `/mock_users 5 1` - Creates 5 mock users for event ID 1
- `/mock_users 20 1 0.5 0.3` - Creates 20 users for event 1, 50% neulings, 30% with partners

**Parameters:**
- `count`: Number of mock users to create (1-100)
- `event_id`: (Optional) Specific event ID. If omitted, uses the first open event
- `neuling_probability`: (Optional) Probability that a user is a neuling (0.0-1.0, default: 0.3)
- `partner_probability`: (Optional) Probability that a user has a partner (0.0-1.0, default: 0.4)

**What Mock Users Do:**
- Mock users simulate the complete registration conversation flow
- They automatically answer all questions (neuling, partner, etc.)
- They are stored in the database just like real users
- Mock user IDs start at 1,000,000 to avoid conflicts with real users
- Mock users are generated with realistic German names (e.g., "Max Müller", "Anna Schmidt")
- Partner names are also realistic - sometimes sharing the same last name (couples) or having different surnames

### Programmatic Testing

You can also create mock users programmatically using Python:

```python
import asyncio
import os
from dotenv import load_dotenv
from telegram.ext import ApplicationBuilder
import database as db
import mock_users

load_dotenv()
TOKEN = os.getenv('TELEGRAM_TOKEN')

async def create_test_users():
    # Create and open an event
    event_id = db.create_event('Test Event', seat_limit=35)
    db.set_event_open(event_id, True)
    
    # Create bot application for context
    application = ApplicationBuilder().token(TOKEN).build()
    await application.initialize()
    
    # Create mock context
    class MockContext:
        def __init__(self, application):
            self.application = application
            self.bot = application.bot
            self._user_data_store = {}
        
        @property
        def user_data(self):
            if not hasattr(self, '_current_user_data'):
                self._current_user_data = {}
            return self._current_user_data
        
        def set_user(self, user_id):
            if user_id not in self._user_data_store:
                self._user_data_store[user_id] = {}
            self._current_user_data = self._user_data_store[user_id]
    
    context = MockContext(application)
    
    # Create mock users
    results = await mock_users.create_mock_users(
        count=15,
        context=context,
        event_id=event_id,
        neuling_probability=0.3,
        partner_probability=0.4
    )
    
    print(f"Created {results['success']} mock users")
    await application.shutdown()

asyncio.run(create_test_users())
```

### Testing Workflow

1. **Create an event**: Use `/create_event Test Event` (as admin)
2. **Open the event**: Use `/admin_open` and select the event
3. **Create mock users**: Use `/mock_users 15` to create 15 test users with realistic names
4. **Check registrations**: Use `/admin_list` to see all registrations
5. **Test allocation**: Use `/admin_close` to close registration and trigger seat allocation
6. **Verify results**: Check that users were allocated correctly (admins first, then neulings, then random)

### Tips for Testing

- **Multiple batches**: You can add more mock users to an existing event by running `/mock_users` again - the system automatically uses the next available user IDs
- **Realistic scenarios**: The default probabilities (30% neulings, 40% with partners) create realistic test scenarios
- **Large groups**: Test with 30-40 users to see how the waiting list works (seat limit is 35 by default)
- **Partner testing**: Partners are treated as a unit - test scenarios where partners both register separately vs. one registering with a partner name
