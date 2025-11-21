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
-   `/register`: Register for the event. You will be asked if you are a "Neuling" and if you have a partner.
-   `/status`: Check your registration status.
-   `/cancel`: Cancel your registration.

### Admin Commands
-   `/admin_open`: Open registration.
-   `/admin_close`: Close registration and run the seat allocation algorithm.

## Seat Allocation Logic
When `/admin_close` is run:
1.  **Admins**: Automatically accepted (plus their partner).
2.  **Neulings**: Automatically accepted (plus their partner).
3.  **Random**: Remaining seats (up to 35 total) are filled randomly from the remaining applicants.
    -   Partners are treated as a unit: either both get in, or neither (if only 1 seat remains).
4.  **Waiting List**: Everyone else is moved to the waiting list.

## Cancellation
If an accepted user cancels:
1.  Their status becomes `CANCELLED`.
2.  The first person on the waiting list is notified.
3.  They receive a message with "Accept" / "Deny" buttons.
