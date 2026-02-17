CN Socket Project – TCP Client-Server



A Computer Networks academic project demonstrating TCP socket programming in Python: a multi-client echo server, a client with input validation and timeouts, and a clear message protocol.



Table of Contents

- [Project Structure](#project-structure)
- [Concepts Used](#concepts-used)
- [Setup Instructions](#setup-instructions)
- [How to Run & Test](#how-to-run--test)
- [Data Flow: Client to Server](#data-flow-client-to-server)
- [OSI Layer Mapping](#osi-layer-mapping)
- [What Happens When a Connection Is Established](#what-happens-when-a-connection-is-established)
- [TCP vs UDP](#tcp-vs-udp)



Project Structure


cn_socket_project/
├── server/
│   ├── __init__.py
│   └── tcp_server.py      # Multi-threaded TCP server
├── client/
│   ├── __init__.py
│   └── tcp_client.py      # TCP client (interactive)
├── utils/
│   ├── __init__.py
│   ├── protocol.py        # Message encode/decode, validation
│   └── logger.py          # Logging setup
├── logs/                  # Created at runtime (server.log, client.log)
├── README.md
└── requirements.txt
```

- **server/** – Server process: bind, listen, accept, handle each client in a thread.
- **client/** – Client process: connect, send, receive, graceful close.
- **utils/** – Shared protocol (length-prefixed messages) and logging.

---

 Concepts Used

| Concept   | Meaning |
|----------|---------|
| **Socket** | An endpoint for sending/receiving data. Created with `socket.socket(AF_INET, SOCK_STREAM)`. Like a “phone” for the application. |
| **Bind**  | Associates the server socket with a specific (IP, port). Without bind, the OS does not know which port to listen on. |
| **Listen**| Puts the socket in listening mode so it can accept connections. The *backlog* limits how many pending connections can wait. |
| **Accept**| Blocks until a client connects; returns a **new** socket for that client and the client’s address. The original socket keeps accepting more clients. |
| **Send**  | Sends bytes to the connected peer. TCP guarantees order and reliability (retransmits if needed). |
| **Recv**  | Receives bytes from the peer. May return fewer bytes than requested; we use a length-prefixed protocol to read complete messages. |

---

Setup Instructions

1. **Python**  
   Use Python **3.8 or newer** (for type hints and standard library).

2. **Clone / copy the project**  
   Ensure the `cn_socket_project` folder is available on your machine.

3. **Optional: virtual environment**
   ```bash
   cd cn_socket_project
   python -m venv venv
   # Windows:
   venv\Scripts\activate
   # Linux/macOS:
   source venv/bin/activate
   ```

4. **Dependencies**  
   Only the standard library is required. To install any optional dev tools:
   ```bash
   pip install -r requirements.txt
   ```

5. **Run from project root**  
   All commands below assume your current directory is `cn_socket_project`.

---

## How to Run & Test

### 1. Start the server

From the **project root** (`cn_socket_project`):

```bash
python -m server.tcp_server
```

Optional arguments:

```bash
python -m server.tcp_server --host 0.0.0.0 --port 5000
```

You should see something like:  
`Server bound to 0.0.0.0:5000` and `Server listening...`

### 2. Start one or more clients

In **another terminal**, from the same project root:

```bash
python -m client.tcp_client
```

Optional:

```bash
python -m client.tcp_client --host 127.0.0.1 --port 5000
```

### 3. Test behavior

- Type a message and press Enter → server echoes it back (e.g. `ECHO: your message`).
- Type `quit`, `exit`, or `q` → client closes the connection.
- Stop the server with **Ctrl+C** → server shuts down and closes client connections.

### 4. Multi-client test

1. Start the server once.
2. Open two or more client terminals and run `python -m client.tcp_client` in each.
3. Send messages from each client; each gets its own echo. This shows **multi-client support via threading**.

### 5. Error cases

- Start the client **without** the server → you should see “Connection refused”.
- On the client, send a very long message (or trigger validation) → check that validation/limits behave as in `utils/protocol.py`.

---

## Data Flow: Client to Server

Step-by-step path of one message from client to server and back:

1. **User types message** (e.g. `Hello`) in the client.
2. **Validation** – `validate_message()` checks non-empty, type, length.
3. **Encode** – `encode_message()` produces: 4-byte length (big-endian) + UTF-8 payload.
4. **Send** – Client socket `send()` passes bytes to the OS. OS TCP stack segments and sends IP packets.
5. **Network** – Packets go over loopback (same machine) or LAN/Internet.
6. **Server OS** – Kernel receives packets, TCP reassembles stream, delivers bytes to the server process.
7. **Server recv** – Server thread reads 4-byte header, then payload length bytes.
8. **Decode** – `decode_message()` turns bytes into a string.
9. **Process** – Server builds response (e.g. `ECHO: Hello`).
10. **Encode & send** – Server encodes and `send()`s response bytes.
11. **Client recv** – Client reads header + payload, decodes.
12. **Display** – Client prints the response to the user.

So: **Application (client) → socket send → TCP → IP → … → IP → TCP → socket recv → Application (server)**, and back the same way.

---

## OSI Layer Mapping

Which OSI layers this project uses:

| Layer   | Name        | Role in this project |
|--------|-------------|-----------------------|
| **7**  | Application | Our code: protocol format, encode/decode, “echo” logic. |
| **6**  | Presentation| Character encoding (UTF-8); we do it in application code. |
| **5**  | Session     | Not explicitly implemented; TCP connection is the “session”. |
| **4**  | Transport   | **TCP** – sockets are `SOCK_STREAM`; TCP provides reliability and ordering. |
| **3**  | Network     | **IP** – used by the OS (e.g. `AF_INET`); we don’t touch IP directly. |
| **2**  | Data Link   | NIC/driver; we don’t implement. |
| **1**  | Physical    | Cables/wireless; we don’t implement. |

**Layers we use:** Application (our code), Transport (TCP), Network (IP via OS). The Python `socket` API hides most of the lower layers.

---

## What Happens When a Connection Is Established

When the client calls `connect()` and the server has called `listen()` and is in `accept()`:

1. **Client: `connect(server_ip, server_port)`**
   - Client TCP sends a **SYN** (synchronize) segment to the server.

2. **Server: TCP receives SYN**
   - Server TCP allocates resources, sends **SYN-ACK** (acknowledgment) back.

3. **Client: receives SYN-ACK**
   - Client sends **ACK**. Connection state becomes “established” on both sides.

4. **Server: `accept()` returns**
   - The OS has completed the 3-way handshake. `accept()` creates a **new** socket for this client and returns it. The listening socket keeps accepting more clients.

5. **Data transfer**
   - Both sides use **send()** and **recv()** on the connection. TCP handles segmentation, acknowledgments, retransmissions, and ordering.

6. **Closing**
   - One side (e.g. client) calls `shutdown(SHUT_WR)` then `close()`. The other side’s `recv()` returns empty; then it closes. TCP performs the 4-way tear-down (FIN/ACK).

Our code does not create SYN/ACK/FIN ourselves; the OS TCP stack does that when we use the socket API.

---

## TCP vs UDP

| Aspect        | TCP (used here)     | UDP                    |
|---------------|---------------------|------------------------|
| Connection    | Connection-oriented (connect, then stream). | Connectionless (no connect; each send is independent). |
| Reliability   | Reliable (retransmits lost packets, in-order delivery). | Best-effort (no retransmission, no ordering guarantee). |
| Socket type   | `SOCK_STREAM`       | `SOCK_DGRAM`           |
| Data          | Byte **stream** (no built-in message boundaries). | **Datagrams** (each send/recv is one message). |
| Use cases     | Web, email, file transfer, this project. | DNS, video streaming, gaming (low latency). |

This project uses **TCP** because we want reliable, ordered delivery and a long-lived connection for multiple request–response exchanges.

