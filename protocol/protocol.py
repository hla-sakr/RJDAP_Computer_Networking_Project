

import struct
import zlib


# ==========================================
# 1. Protocol constants
# ==========================================

PROTOCOL_VERSION = 1

HEADER_FORMAT = "!BBIHHHI"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)  # 16 bytes

MAX_PACKET_SIZE = 512
MAX_PAYLOAD_SIZE = MAX_PACKET_SIZE - HEADER_SIZE  # 496 bytes


# ==========================================
# 2. Message type codes
# ==========================================

WORKER_JOIN = 1
HEARTBEAT = 2
TASK_DISPATCH = 3
TASK_RESULT = 4
ACK_RESULT = 5
WORKER_ACCEPT = 6

VALID_MESSAGE_TYPES = {
    WORKER_JOIN,
    HEARTBEAT,
    TASK_DISPATCH,
    TASK_RESULT,
    ACK_RESULT,
    WORKER_ACCEPT,
}


# ==========================================
# 3. Task result status codes
# ==========================================

SUCCESS = 1
NOT_FOUND = 2
ERROR = 3

VALID_STATUSES = {SUCCESS, NOT_FOUND, ERROR}


# ==========================================
# 4. Payload validation
# ==========================================

def validate_payload(message_type, payload):
    """Check that a message has the expected payload size."""

    expected_sizes = {
        WORKER_JOIN: 0,
        HEARTBEAT: 0,
        TASK_DISPATCH: 12,
        TASK_RESULT: 5,
        ACK_RESULT: 0,
        WORKER_ACCEPT: 0,
    }

    if message_type not in expected_sizes:
        raise ValueError("Unknown message type")

    expected = expected_sizes[message_type]

    if len(payload) != expected:
        raise ValueError(
            f"Invalid payload size: expected {expected}, "
            f"received {len(payload)}"
        )


# ==========================================
# 5. Encode a complete RJDAP packet
# ==========================================

def encode_message(
    message_type,
    task_id=0,
    worker_id=0,
    attempt_num=0,
    payload=b"",
):
    """Build a complete packet: 16-byte header + payload."""

    if message_type not in VALID_MESSAGE_TYPES:
        raise ValueError("Unknown message type")

    if not isinstance(payload, bytes):
        raise TypeError("Payload must be bytes")

    validate_payload(message_type, payload)

    if len(payload) > MAX_PAYLOAD_SIZE:
        raise ValueError("Payload exceeds the packet size limit")

    payload_length = len(payload)

    # Calculate CRC32 over the payload only.
    checksum = zlib.crc32(payload) & 0xFFFFFFFF

    header = struct.pack(
        HEADER_FORMAT,
        PROTOCOL_VERSION,
        message_type,
        task_id,
        worker_id,
        attempt_num,
        payload_length,
        checksum,
    )

    packet = header + payload

    if len(packet) > MAX_PACKET_SIZE:
        raise ValueError("Packet exceeds 512 bytes")

    return packet


# ==========================================
# 6. Decode and validate a complete packet
# ==========================================

def decode_message(packet):
    """Validate a received packet and extract its fields."""

    if not isinstance(packet, bytes):
        raise TypeError("Packet must be bytes")

    if len(packet) < HEADER_SIZE:
        raise ValueError("Packet is shorter than the header")

    if len(packet) > MAX_PACKET_SIZE:
        raise ValueError("Packet exceeds 512 bytes")

    header = packet[:HEADER_SIZE]
    payload = packet[HEADER_SIZE:]

    (
        version,
        message_type,
        task_id,
        worker_id,
        attempt_num,
        payload_length,
        received_checksum,
    ) = struct.unpack(HEADER_FORMAT, header)

    if version != PROTOCOL_VERSION:
        raise ValueError("Unsupported protocol version")

    if message_type not in VALID_MESSAGE_TYPES:
        raise ValueError("Unknown message type")

    if payload_length != len(payload):
        raise ValueError("Payload length does not match header")

    validate_payload(message_type, payload)

    calculated_checksum = zlib.crc32(payload) & 0xFFFFFFFF

    if calculated_checksum != received_checksum:
        raise ValueError("Payload checksum mismatch")

    return {
        "version": version,
        "message_type": message_type,
        "task_id": task_id,
        "worker_id": worker_id,
        "attempt_num": attempt_num,
        "payload_length": payload_length,
        "payload": payload,
    }


# ==========================================
# 7. TASK_DISPATCH payload helpers
# ==========================================

def encode_task_dispatch(start, end, target):
    """Encode three unsigned 32-bit integers."""

    if start >= end:
        raise ValueError("Start must be smaller than end")

    return struct.pack("!III", start, end, target)


def decode_task_dispatch(payload):
    """Decode start, end, and target."""

    if len(payload) != 12:
        raise ValueError("TASK_DISPATCH payload must be 12 bytes")

    start, end, target = struct.unpack("!III", payload)

    if start >= end:
        raise ValueError("Invalid task range")

    return {
        "start": start,
        "end": end,
        "target": target,
    }


# ==========================================
# 8. TASK_RESULT payload helpers
# ==========================================

def encode_task_result(status, result):
    """Encode a one-byte status and a 32-bit result."""

    if status not in VALID_STATUSES:
        raise ValueError("Invalid result status")

    return struct.pack("!BI", status, result)


def decode_task_result(payload):
    """Decode status and numeric result."""

    if len(payload) != 5:
        raise ValueError("TASK_RESULT payload must be 5 bytes")

    status, result = struct.unpack("!BI", payload)

    if status not in VALID_STATUSES:
        raise ValueError("Invalid result status")

    return {
        "status": status,
        "result": result,
    }
