"""Event platform: surface received Becker remote presses as HA events."""

from .const import COMMANDS


def decode_event_type(command: bytes, argument: bytes) -> str:
    """Map a received command/argument nibble pair to an event type.

    Tries the exact command+argument byte first (which distinguishes the
    intermediate positions), then command+"0" (argument nibble not
    meaningful), then falls back to "unknown" so nothing is dropped.
    """
    reverse = {code: name for name, code in COMMANDS.items()}
    return reverse.get(command + argument) or reverse.get(command + b"0") or "unknown"
