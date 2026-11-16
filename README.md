# RJDAP_Computer_Networking_Project
# RJDAP – Reliable Job Dispatch & Aggregation Protocol

**Team 8 – Computer Networks Major Task, Fall 2026 (Project 2)**
**Phase 1: Prototype**

RJDAP is a custom application-layer protocol that runs over **UDP**. A central
server (the *Command Hub*) registers worker clients, monitors their liveness
with heartbeats, dispatches computation tasks, and acknowledges the results
that workers return. Packets use a custom 16-byte binary header with a CRC32
checksum over the payload.

## Demo video

**Link:** ``


## 1. Requirements

- **Python 3.8 or newer** (developed and tested with Python 3.12)
- **No third-party packages.** Only the standard library is used
  (`socket`, `struct`, `zlib`, `time`, `unittest`).
- Works on Windows, Linux, and macOS. The server and worker both run on
  `127.0.0.1`, so no network setup or administrator rights are needed.

On Windows use `python`. On Linux/macOS use `python3` in place of `python`
in every command below.

## 2. Project structure

```
RJDAP/
├── protocol/
│   ├── protocol.py          # Packet format: header, encoding, decoding, validation
│   └── test_protocol.py     # Unit tests for the protocol module
├── server/
│   ├── server.py            # UDP server (main loop and message handlers)
│   └── worker_manager.py    # Worker registry, ID assignment, heartbeat tracking
├── worker/
│   ├── test_worker.py       # Prototype worker used for the Phase 1 demo
│   └── worker.py            # Reserved for the full worker client (Phase 2)
├── documentation/           # Project proposal and Mini-RFC draft
└── README.md
```

## 3. Running the prototype locally

You need **two terminals**, both opened in the project root folder.

### Step 1 – Start the server (Terminal 1)

```
python server/server.py
```

Expected output:

```
RJDAP Server started.
Listening on 127.0.0.1:2006
```

The server keeps running until you stop it with `Ctrl+C`.

### Step 2 – Start a worker (Terminal 2)

```
python worker/test_worker.py
```

The worker performs one complete session and then exits:

1. Sends `WORKER_JOIN` and receives `WORKER_ACCEPT` with its assigned Worker ID.
2. Sends a `HEARTBEAT`.
3. Receives a `TASK_DISPATCH`, runs the computation, and sends a `TASK_RESULT`.
4. Receives the `ACK_RESULT` for that task.
5. Sends a deliberately malformed packet to show that the server rejects it.

### Expected output

**Worker terminal**

```
WORKER_JOIN sent.
WORKER_ACCEPT received!
Assigned Worker ID: 1
HEARTBEAT sent.

TASK_DISPATCH received!
Task ID: 1
Task range: 1 to 100
...
TASK_RESULT sent to server.
ACK_RESULT received!
Task 1 successfully acknowledged.

Invalid packet sent.

Worker socket closed.
```

**Server terminal**

```
WORKER_JOIN received from ('127.0.0.1', <port>)
Worker 1 registered.
WORKER_ACCEPT sent. Assigned Worker ID: 1
TASK_DISPATCH sent to Worker 1
Heartbeat received from Worker 1

TASK_RESULT received from Worker 1
Task ID: 1
...
ACK_RESULT sent to Worker 1
Invalid packet received: Packet is shorter than the header
Worker 1 is now INACTIVE.
```

The last line appears about 6 seconds after the worker exits. The worker has
stopped sending heartbeats, so the server marks it `INACTIVE`. This
demonstrates worker failure detection.

(The `...` lines show the task range and computed result, which depend on the
task the server dispatches.)

### Stopping

Press `Ctrl+C` in the server terminal.

## 4. Running the unit tests

```
cd protocol
python -m unittest -v test_protocol
```

All tests should pass (`OK`). They cover encoding and decoding of every
message type, per-message header rules, payload validation, checksum
verification, corrupted, truncated and oversized packets, and decoder
robustness against random input.

## 5. Configuration

| Setting | File | Default |
|---|---|---|
| Server IP and port | `server/server.py` (`SERVER_IP`, `SERVER_PORT`) | `127.0.0.1`, `2006` |
| Server address used by the worker | `worker/test_worker.py` (`SERVER_ADDRESS`) | `("127.0.0.1", 2006)` |
| Heartbeat timeout | `server/worker_manager.py` (`HEARTBEAT_TIMEOUT`) | 6 seconds |

## 6. Protocol summary

### Packet header (16 bytes, big-endian, `struct` format `!BBIHHHI`)

| Field | Size | Offset | Meaning |
|---|---|---|---|
| Version | 1 byte | 0 | Protocol version (currently 1) |
| Message Type | 1 byte | 1 | See message table below |
| Task ID | 4 bytes | 2–5 | Task the message refers to (0 = none) |
| Worker ID | 2 bytes | 6–7 | Worker involved (0 = not yet assigned) |
| Attempt Number | 2 bytes | 8–9 | Dispatch attempt, starting at 1 |
| Payload Length | 2 bytes | 10–11 | Payload size in bytes |
| Payload Checksum | 4 bytes | 12–15 | CRC32 of the payload |

The maximum packet size (header + payload) is **512 bytes**.

### Message types

| Code | Message | Direction | Payload |
|---|---|---|---|
| 1 | `WORKER_JOIN` | Worker → Server | none |
| 2 | `HEARTBEAT` | Worker → Server | none |
| 3 | `TASK_DISPATCH` | Server → Worker | 12 bytes: start, end, target (3 × uint32) |
| 4 | `TASK_RESULT` | Worker → Server | 5 bytes: status (uint8), result (uint32) |
| 5 | `ACK_RESULT` | Server → Worker | none |
| 6 | `WORKER_ACCEPT` | Server → Worker | none (the assigned Worker ID is in the header) |

`WORKER_ACCEPT` is an extension to the five message types required by the
project description. It tells a new worker which Worker ID it was assigned.

Result status codes: `1` = SUCCESS, `2` = NOT_FOUND, `3` = ERROR.

### Header rules enforced by the protocol module

| Message | Task ID | Worker ID | Attempt Number |
|---|---|---|---|
| `WORKER_JOIN` | 0 | 0 | 0 |
| `HEARTBEAT` | 0 | > 0 | 0 |
| `TASK_DISPATCH` | > 0 | > 0 | ≥ 1 |
| `TASK_RESULT` | > 0 | > 0 | ≥ 1 |
| `ACK_RESULT` | > 0 | > 0 | ≥ 1 |
| `WORKER_ACCEPT` | 0 | > 0 | 0 |

Packets that violate these rules, or that have a wrong version, unknown
message type, wrong length, or a checksum mismatch, are rejected by
`decode_message()` with a `ValueError`. The server logs them and continues.

## 7. Current status (Phase 1)

**Implemented**

- Custom binary protocol with encoding, decoding, validation, and unit tests
- UDP server with worker registration, unique Worker IDs, and heartbeat tracking
- Worker failure detection (`INACTIVE` after missing heartbeats)
- One complete exchange: join → accept → heartbeat → dispatch → result → ACK
- Rejection of malformed packets without crashing the server

**Not yet implemented (planned for Phase 2)**

- The 1,000-task queue and scheduling across four workers
- Task timeouts and reassignment
- Result retransmission and duplicate-result suppression
- The four `netem` test scenarios, logs, pcap captures, and CSV measurements

## 8. Troubleshooting

| Problem | Cause and fix |
|---|---|
| `Server did not respond within the expected time.` | The server is not running, or it uses a different port. Start `server/server.py` first and check the port in both files. |
| `OSError: [Errno 98]` or `[WinError 10048]` (address already in use) | An old server is still running. Stop it with `Ctrl+C` or close its terminal. |
| `ModuleNotFoundError: No module named 'protocol'` or `module 'protocol' has no attribute ...` | `protocol.py` was not found. Run the commands from the project root and keep the folder layout from section 2. |
| Worker shows `Communication error: ...` | The server sent a packet the worker rejected. Check the server terminal for the matching message. |
