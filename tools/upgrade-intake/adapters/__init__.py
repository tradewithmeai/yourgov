"""Channel adapters for upgrade-intake.

Each adapter splits cleanly into:

- a *fetch* part that does IO (network / IMAP / file read), and
- a *normalize* part that is pure: raw payload -> queue record via core.

Tests exercise the pure normalize functions with sample data and never touch
a socket.
"""
