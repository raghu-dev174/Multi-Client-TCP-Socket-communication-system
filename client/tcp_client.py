"""
TCP Client - Connects to the server and sends/receives messages.

This module implements a TCP client that:
- Connects to a server at a given host and port
- Sends user messages using the same length-prefixed protocol as the server
- Receives and displays responses with timeout handling
- Validates input and closes the connection gracefully

SOCKET CONCEPTS (recap):
- SOCKET: Endpoint for communication. Client creates a socket and uses it to
  connect to the server's address.
- CONNECT: (Client-side only.) Initiates the TCP 3-way handshake with the
  server. After connect() returns, the connection is established.
- SEND: Sends data to the server. Data must be bytes. TCP guarantees order
  and reliability (retransmits if packets are lost).
- RECV: Receives data from the server. Returns bytes. May return less than
  requested; we loop until we have the full message (using our protocol).
- CLOSE: Closes the connection. Proper close: shutdown(SHUT_WR) then recv
  until 0, then close() - so both sides know the stream is finished.
"""

import socket
import sys
from pathlib import Path

# Add project root to path so we can import utils
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.logger import setup_logger
from utils.protocol import (
    encode_message,
    decode_message,
    validate_message,
    MAX_MESSAGE_SIZE,
    HEADER_SIZE,
)

# --- Client Configuration ---
DEFAULT_HOST = "127.0.0.1"  # Localhost (same machine)
DEFAULT_PORT = 5000
CONNECT_TIMEOUT = 10.0  # Seconds to wait when connecting
RECV_TIMEOUT = 30.0     # Seconds to wait for server response


def receive_message(sock: socket.socket) -> str | None:
    """
    Read one length-prefixed message from the socket.
    Returns the decoded string, or None if connection was closed.
    """
    # Read header (4 bytes)
    header = b""
    while len(header) < HEADER_SIZE:
        chunk = sock.recv(HEADER_SIZE - len(header))
        if not chunk:
            return None
        header += chunk

    import struct
    (length,) = struct.unpack(">I", header)
    if length > MAX_MESSAGE_SIZE:
        raise ValueError(f"Invalid message length from server: {length}")

    payload = b""
    while len(payload) < length:
        to_read = min(4096, length - len(payload))
        chunk = sock.recv(to_read)
        if not chunk:
            return None
        payload += chunk

    return decode_message(header + payload)


def run_client(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    """
    Connect to the server and run the interactive send/receive loop.
    """
    logger = setup_logger("client", log_file="logs/client.log")

    # --- Create socket (same as server: AF_INET, SOCK_STREAM for TCP) ---
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.settimeout(RECV_TIMEOUT)

    try:
        # --- CONNECT: Establish connection to the server ---
        # This triggers the TCP 3-way handshake. Blocks until connected or timeout.
        logger.info("Connecting to %s:%s...", host, port)
        client_socket.settimeout(CONNECT_TIMEOUT)
        client_socket.connect((host, port))
        client_socket.settimeout(RECV_TIMEOUT)
        logger.info("Connected to %s:%s", host, port)

        print("\nConnected to server. Type your message and press Enter.")
        print("Commands: 'quit' or 'exit' to close, 'q' to quit.\n")

        while True:
            try:
                # Get user input
                user_input = input("You > ").strip()

                # --- Input validation ---
                if not user_input:
                    print("(Empty message ignored. Type something or 'quit' to exit.)")
                    continue

                if user_input.lower() in ("quit", "exit", "q"):
                    print("Closing connection...")
                    break

                is_valid, err_msg = validate_message(user_input)
                if not is_valid:
                    print(f"Invalid input: {err_msg}")
                    continue

                # --- Encode and send ---
                message_bytes = encode_message(user_input)
                total_sent = 0
                while total_sent < len(message_bytes):
                    sent = client_socket.send(message_bytes[total_sent:])
                    if sent == 0:
                        raise RuntimeError("Connection broken.")
                    total_sent += sent
                logger.debug("Sent: %s", user_input)

                # --- Receive response ---
                response = receive_message(client_socket)
                if response is None:
                    print("Server closed the connection.")
                    break
                print(f"Server > {response}")
                logger.debug("Received: %s", response)

            except socket.timeout:
                print("No response from server (timeout). Try again or type 'quit' to exit.")
                logger.warning("Receive timeout")
            except (ConnectionResetError, BrokenPipeError, OSError) as e:
                print(f"Connection error: {e}")
                logger.error("Connection error: %s", e)
                break

    except socket.timeout:
        print("Connection timed out. Is the server running?")
        logger.error("Connect timeout to %s:%s", host, port)
    except ConnectionRefusedError:
        print("Connection refused. Is the server running on %s:%s?" % (host, port))
        logger.error("Connection refused: %s:%s", host, port)
    except OSError as e:
        print(f"Network error: {e}")
        logger.exception("Network error: %s", e)
    finally:
        # --- Graceful close: shutdown write side, drain read side, then close ---
        try:
            # SHUT_WR: No more sends. Server will get EOF and can close its side.
            client_socket.shutdown(socket.SHUT_WR)
        except OSError:
            pass
        try:
            # Drain any remaining data so server's close is clean
            while client_socket.recv(4096):
                pass
        except (socket.timeout, OSError):
            pass
        try:
            client_socket.close()
        except OSError:
            pass
        logger.info("Disconnected from %s:%s", host, port)
        print("Goodbye.")


def main() -> None:
    """Entry point: parse host/port from command line and run the client."""
    import argparse
    parser = argparse.ArgumentParser(description="TCP Echo Client (CN Socket Project)")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Server host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Server port (default: 5000)")
    args = parser.parse_args()

    run_client(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
