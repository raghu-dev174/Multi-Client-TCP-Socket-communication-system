"""
Protocol Module - Message format and validation for TCP communication.

This module defines how client and server exchange messages.
Using a clear protocol ensures both sides interpret data correctly.

PROTOCOL FORMAT (simple and beginner-friendly):
    Each message = LENGTH (4 bytes, big-endian integer) + PAYLOAD (UTF-8 bytes)
    Example: length 11, payload "Hello World" -> b'\\x00\\x00\\x00\\x0bHello World'
"""

import struct
from typing import Tuple

# --- Protocol Constants ---
# Version number for future protocol changes (e.g., v2 could add encryption)
PROTOCOL_VERSION = 1

# Maximum message size in bytes (prevents memory exhaustion from huge messages)
# 64 KB is a reasonable limit for text messages
MAX_MESSAGE_SIZE = 65536

# Character encoding for converting between string and bytes
# UTF-8 supports all Unicode characters and is the standard for network text
ENCODING = "utf-8"

# Length of the length header in bytes (we use 4 bytes = 32-bit integer)
# This allows messages up to ~4 GB (we still enforce MAX_MESSAGE_SIZE)
HEADER_SIZE = 4


def encode_message(text: str) -> bytes:
    """
    Encode a string message into the wire format: [4-byte length][payload bytes].

    Args:
        text: The message string to send (will be encoded as UTF-8).

    Returns:
        bytes: Length-prefixed message ready to send over the socket.

    Raises:
        ValueError: If text is empty or exceeds MAX_MESSAGE_SIZE.
    """
    if not text or not text.strip():
        raise ValueError("Message cannot be empty or whitespace only.")

    # Encode string to bytes using UTF-8 (network standard for text)
    payload = text.encode(ENCODING)

    if len(payload) > MAX_MESSAGE_SIZE:
        raise ValueError(
            f"Message too long. Max size is {MAX_MESSAGE_SIZE} bytes, got {len(payload)}."
        )

    # struct.pack: '>' = big-endian (network byte order), 'I' = unsigned int (4 bytes)
    # Big-endian is the standard for network protocols (see RFC 1700)
    length_header = struct.pack(">I", len(payload))

    # Concatenate header + payload so receiver knows exactly how many bytes to read
    return length_header + payload


def decode_message(data: bytes) -> str:
    """
    Decode wire format bytes back into a string message.

    Args:
        data: Raw bytes received (must be at least HEADER_SIZE bytes).

    Returns:
        str: The decoded message string.

    Raises:
        ValueError: If data is too short or invalid.
    """
    if len(data) < HEADER_SIZE:
        raise ValueError(
            f"Invalid message: too short. Need at least {HEADER_SIZE} bytes for header."
        )

    # Unpack the first 4 bytes as big-endian unsigned int
    (length,) = struct.unpack(">I", data[:HEADER_SIZE])

    if length > MAX_MESSAGE_SIZE:
        raise ValueError(
            f"Invalid message: length {length} exceeds max {MAX_MESSAGE_SIZE}."
        )

    payload = data[HEADER_SIZE : HEADER_SIZE + length]

    if len(payload) != length:
        raise ValueError(
            f"Invalid message: payload length {len(payload)} does not match header {length}."
        )

    # Decode UTF-8 bytes to string (raises UnicodeDecodeError if invalid)
    return payload.decode(ENCODING)


def validate_message(text: str) -> Tuple[bool, str]:
    """
    Validate a message before sending (input validation).

    Args:
        text: The message string to validate.

    Returns:
        Tuple of (is_valid, error_message). If valid, error_message is empty.
    """
    if text is None:
        return False, "Message cannot be None."
    if not isinstance(text, str):
        return False, "Message must be a string."
    if not text.strip():
        return False, "Message cannot be empty or whitespace only."
    if len(text.encode(ENCODING)) > MAX_MESSAGE_SIZE:
        return False, f"Message exceeds maximum size of {MAX_MESSAGE_SIZE} bytes."
    return True, ""
