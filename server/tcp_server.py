"""
TCP Server - Multi-client server using threading.

This module implements a TCP server that:
- Listens for incoming connections
- Handles each client in a separate thread (multi-client support)
- Uses a clear message protocol and logging
- Supports graceful shutdown and timeout handling

NETWORKING CONCEPTS (brief):
- SOCKET: An endpoint for sending/receiving data. Think of it as a "phone" that
  can call or be called. Created with socket.socket(family, type).
- BIND: Associates the socket with a specific (IP address, port) on the server.
  Without bind, the OS wouldn't know which port to listen on.
- LISTEN: Puts the socket in "listening" mode. It can now accept incoming
  connection requests. The backlog argument limits how many pending connections
  can wait in the queue.
- ACCEPT: Blocks until a client connects, then returns a NEW socket for that
  client and the client's address. The original socket keeps accepting more clients.
- SEND / RECV: Send transmits data to the connected peer; recv reads data from
  the peer. For TCP, data is a byte stream (no message boundaries), so we use
  our protocol (length-prefixed) to know how much to read.
"""

import socket
import threading
import signal
import sys
from pathlib import Path
from typing import Set

# Add project root to path so we can import utils
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.logger import setup_logger
from utils.protocol import (
    encode_message,
    decode_message,
    MAX_MESSAGE_SIZE,
    HEADER_SIZE,
)

# --- Server Configuration ---
DEFAULT_HOST = "0.0.0.0"  # Listen on all interfaces (so clients can connect from other machines)
DEFAULT_PORT = 5000
BACKLOG = 5  # Max number of pending connections in the queue (see "listen" below)
RECV_TIMEOUT = 30.0  # Seconds to wait for data from client before timing out
SHUTDOWN_TIMEOUT = 2.0  # Seconds to wait for threads to finish on shutdown

# Global flag for graceful shutdown (set by signal handler)
shutdown_requested = False
# Lock to protect shared state (e.g., client set)
lock = threading.Lock()
# Set of active client sockets (so we can close them on shutdown)
active_clients: Set[socket.socket] = set()


def handle_client(client_socket: socket.socket, client_address: tuple) -> None:
    """
    Handle communication with a single client. Runs in a dedicated thread.

    This function runs in a loop: receive message -> process -> send response,
    until the client disconnects or an error occurs.

    Args:
        client_socket: The socket connected to this client (returned by accept()).
        client_address: (ip, port) of the client for logging.
    """
    client_ip, client_port = client_address
    logger = setup_logger("server")
    logger.info("Client connected: %s:%s", client_ip, client_port)

    # Add to active set so we can close on shutdown
    with lock:
        active_clients.add(client_socket)

    try:
        while not shutdown_requested:
            # --- Receive message (length-prefixed protocol) ---
            # Step 1: Read exactly HEADER_SIZE bytes to get the length
            header = b""
            while len(header) < HEADER_SIZE:
                chunk = client_socket.recv(HEADER_SIZE - len(header))
                if not chunk:
                    # Connection closed by client (recv returns empty when peer shuts down)
                    logger.info("Client %s:%s closed connection.", client_ip, client_port)
                    return
                header += chunk

            (length,) = __parse_header(header)
            if length > MAX_MESSAGE_SIZE:
                logger.warning("Client sent invalid length %s; closing connection.", length)
                return

            # Step 2: Read exactly 'length' bytes of payload
            payload = b""
            while len(payload) < length:
                to_read = length - len(payload)
                chunk = client_socket.recv(min(4096, to_read))
                if not chunk:
                    logger.info("Connection closed while reading payload.")
                    return
                payload += chunk

            message = decode_message(header + payload)
            logger.info("Received from %s:%s: %s", client_ip, client_port, message)

            # --- Process and respond (echo server: send back the same message) ---
            response = f"ECHO: {message}"
            response_bytes = encode_message(response)
            # send() may not send all bytes in one call; we loop until all sent
            total_sent = 0
            while total_sent < len(response_bytes):
                sent = client_socket.send(response_bytes[total_sent:])
                if sent == 0:
                    raise RuntimeError("Socket connection broken.")
                total_sent += sent

            logger.debug("Sent response to %s:%s", client_ip, client_port)

    except socket.timeout:
        logger.warning("Timeout waiting for data from %s:%s", client_ip, client_port)
    except (ConnectionResetError, BrokenPipeError, OSError) as e:
        logger.info("Client %s:%s disconnected or error: %s", client_ip, client_port, e)
    except Exception as e:
        logger.exception("Unexpected error handling client %s:%s: %s", client_ip, client_port, e)
    finally:
        # Always remove from set and close the socket
        with lock:
            active_clients.discard(client_socket)
        try:
            client_socket.close()
        except OSError:
            pass
        logger.info("Client %s:%s handling finished.", client_ip, client_port)


def __parse_header(header: bytes) -> tuple[int]:
    """Parse 4-byte big-endian length header. Returns (length,)."""
    import struct
    return struct.unpack(">I", header)


def run_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    """
    Create the server socket, bind, listen, and accept clients in a loop.
    Each client is handled in a new thread.
    """
    global shutdown_requested
    logger = setup_logger("server", log_file="logs/server.log")

    # --- Create socket ---
    # socket.AF_INET = IPv4. AF_INET6 would be IPv6.
    # socket.SOCK_STREAM = TCP (reliable, connection-oriented, byte stream).
    # SOCK_DGRAM would be UDP (unreliable, connectionless, datagram).
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # Allow reusing the address so we can restart the server without "Address already in use"
    # SO_REUSEADDR lets the OS reuse the port after the previous server closed
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    # Set receive timeout so we don't block forever; handle_client will see this on recv
    server_socket.settimeout(1.0)  # Short timeout on accept loop so we can check shutdown_requested

    try:
        # --- BIND: Attach the socket to (host, port) ---
        # The server will listen on this address. 0.0.0.0 means "all interfaces".
        server_socket.bind((host, port))
        logger.info("Server bound to %s:%s", host, port)

        # --- LISTEN: Put socket in listening mode ---
        # BACKLOG: How many pending connections can wait in the queue. If the server
        # is busy, new connections can queue up; beyond backlog they may get refused.
        server_socket.listen(BACKLOG)
        logger.info("Server listening (backlog=%s). Waiting for connections...", BACKLOG)

        # --- ACCEPT loop: Accept new clients and spawn a thread for each ---
        while not shutdown_requested:
            try:
                # ACCEPT: Blocks until a client connects. Returns (new_socket, client_address).
                # The new socket is used only for this client; the server_socket keeps accepting.
                client_socket, client_address = server_socket.accept()

                # Set timeout for this client so we don't block forever on recv
                client_socket.settimeout(RECV_TIMEOUT)

                # Create a new thread to handle this client (so we can serve many at once)
                thread = threading.Thread(
                    target=handle_client,
                    args=(client_socket, client_address),
                    daemon=True,  # Daemon threads exit when main thread exits
                )
                thread.start()

            except socket.timeout:
                # Normal: we set a 1s timeout so we can check shutdown_requested
                continue
            except OSError as e:
                if shutdown_requested:
                    break
                logger.error("Accept error: %s", e)
                break

    finally:
        # --- Graceful shutdown: close all client connections and then server socket ---
        logger.info("Shutting down server...")
        shutdown_requested = True

        with lock:
            for sock in list(active_clients):
                try:
                    sock.close()
                except OSError:
                    pass
            active_clients.clear()

        try:
            server_socket.close()
        except OSError:
            pass
        logger.info("Server stopped.")


def main() -> None:
    """Entry point: parse optional host/port from command line and run the server."""
    import argparse
    parser = argparse.ArgumentParser(description="TCP Echo Server (CN Socket Project)")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Host to bind to (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to bind to (default: 5000)")
    args = parser.parse_args()

    # Handle Ctrl+C for graceful shutdown
    def signal_handler(signum, frame):
        global shutdown_requested
        shutdown_requested = True

    signal.signal(signal.SIGINT, signal_handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, signal_handler)

    run_server(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
