# EventBot

A Telegram bot for managing event registrations with automatic seat allocation.

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

## Commands

### User Commands
-   `/start`: Welcome message.
-   `/register`: Register for an event. If multiple events are open, you will be asked to select one.
-   `/status`: Check your registration status for all events.
-   `/cancel`: Cancel your registration for a specific event.

### Admin Commands
-   `/create_event <name>`: Create a new event (e.g., `/create_event Stammtisch Dec`).
-   `/admin_open`: Open registration for a specific event.
-   `/admin_close`: Close registration for a specific event and run the seat allocation algorithm.
-   `/admin_list`: View registrations for a specific event.

## Seat Allocation Logic
When `/admin_close` is run for an event:
1.  **Admins**: Automatically accepted (plus their partner).
2.  **Neulings**: Automatically accepted (plus their partner).
3.  **Random**: Remaining seats (up to 35 per event) are filled randomly from the remaining applicants.
    -   Partners are treated as a unit: either both get in, or neither (if only 1 seat remains).
4.  **Waiting List**: Everyone else is moved to the waiting list for that event.

## Cancellation
If an accepted user cancels:
1.  Their status becomes `CANCELLED`.
2.  The first person on the waiting list for that event is notified.
3.  They receive a message with "Accept" / "Deny" buttons.
