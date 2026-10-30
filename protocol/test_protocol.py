import random
import struct
import unittest
import zlib

from protocol import (
    PROTOCOL_VERSION,
    HEADER_FORMAT,
    HEADER_SIZE,
    MAX_PACKET_SIZE,
    MAX_PAYLOAD_SIZE,

    WORKER_JOIN,
    HEARTBEAT,
    TASK_DISPATCH,
    TASK_RESULT,
    ACK_RESULT,
    WORKER_ACCEPT,

    SUCCESS,
    NOT_FOUND,
    ERROR,

    encode_message,
    decode_message,
    validate_payload,
    validate_header_fields,

    encode_task_dispatch,
    decode_task_dispatch,
    encode_task_result,
    decode_task_result,
)


# ==========================================
# 0. Shared test data and helpers
# ==========================================

DISPATCH_PAYLOAD = encode_task_dispatch(0, 100, 50)
RESULT_PAYLOAD = encode_task_result(SUCCESS, 50)

# One valid message of every type:
# (message_type, task_id, worker_id, attempt_num, payload)
VALID_MESSAGES = [
    (WORKER_JOIN, 0, 0, 0, b""),
    (HEARTBEAT, 0, 7, 0, b""),
    (TASK_DISPATCH, 25, 7, 1, DISPATCH_PAYLOAD),
    (TASK_RESULT, 25, 7, 1, RESULT_PAYLOAD),
    (ACK_RESULT, 25, 7, 1, b""),
    (WORKER_ACCEPT, 0, 7, 0, b""),
]

# Header values that violate the per-message-type rules.
# Each entry has a correct payload size, so the header rule is the
# only thing that can cause the rejection.
INVALID_HEADERS = [
    # WORKER_JOIN: Task_ID=0, Worker_ID=0, Attempt_Num=0
    (WORKER_JOIN, 10, 0, 0, b""),
    (WORKER_JOIN, 0, 5, 0, b""),
    (WORKER_JOIN, 0, 0, 1, b""),

    # HEARTBEAT: Task_ID=0, Worker_ID>0, Attempt_Num=0
    (HEARTBEAT, 10, 5, 0, b""),
    (HEARTBEAT, 0, 0, 0, b""),
    (HEARTBEAT, 0, 5, 1, b""),

    # TASK_DISPATCH: Task_ID>0, Worker_ID>0, Attempt_Num>=1
    (TASK_DISPATCH, 0, 5, 1, DISPATCH_PAYLOAD),
    (TASK_DISPATCH, 10, 0, 1, DISPATCH_PAYLOAD),
    (TASK_DISPATCH, 10, 5, 0, DISPATCH_PAYLOAD),

    # TASK_RESULT: Task_ID>0, Worker_ID>0, Attempt_Num>=1
    (TASK_RESULT, 0, 5, 1, RESULT_PAYLOAD),
    (TASK_RESULT, 10, 0, 1, RESULT_PAYLOAD),
    (TASK_RESULT, 10, 5, 0, RESULT_PAYLOAD),

    # ACK_RESULT: Task_ID>0, Worker_ID>0, Attempt_Num>=1
    (ACK_RESULT, 0, 5, 1, b""),
    (ACK_RESULT, 10, 0, 1, b""),
    (ACK_RESULT, 10, 5, 0, b""),

    # WORKER_ACCEPT: Task_ID=0, Worker_ID>0, Attempt_Num=0
    (WORKER_ACCEPT, 10, 5, 0, b""),
    (WORKER_ACCEPT, 0, 0, 0, b""),
    (WORKER_ACCEPT, 0, 5, 1, b""),
]


def build_raw_packet(message_type, task_id, worker_id, attempt_num,
                     payload=b""):
    """
    Build a packet WITHOUT using protocol.py's validation.

    The header is structurally correct (right length field, right CRC32),
    so any rejection comes from the field rules, not from a framing error.
    This simulates a packet received from a misbehaving sender.
    """

    header = struct.pack(
        HEADER_FORMAT,
        PROTOCOL_VERSION,
        message_type,
        task_id,
        worker_id,
        attempt_num,
        len(payload),
        zlib.crc32(payload) & 0xFFFFFFFF,
    )

    return header + payload


# ==========================================
# 1. Protocol constants tests
# ==========================================

class TestProtocolConstants(unittest.TestCase):

    def test_header_is_exactly_16_bytes(self):
        self.assertEqual(HEADER_SIZE, 16)
        self.assertEqual(struct.calcsize(HEADER_FORMAT), 16)

    def test_packet_size_limit(self):
        self.assertEqual(MAX_PACKET_SIZE, 512)
        self.assertEqual(MAX_PAYLOAD_SIZE, 496)

    def test_protocol_version(self):
        self.assertEqual(PROTOCOL_VERSION, 1)


# ==========================================
# 2. Message encoding and decoding tests
# ==========================================

class TestMessageEncoding(unittest.TestCase):

    def test_all_message_types_round_trip(self):
        """Every supported message type should encode and decode."""

        for msg_type, task_id, worker_id, attempt, payload in VALID_MESSAGES:
            with self.subTest(message_type=msg_type):

                packet = encode_message(
                    msg_type,
                    task_id,
                    worker_id,
                    attempt,
                    payload,
                )

                decoded = decode_message(packet)

                self.assertEqual(decoded["message_type"], msg_type)
                self.assertEqual(decoded["task_id"], task_id)
                self.assertEqual(decoded["worker_id"], worker_id)
                self.assertEqual(decoded["attempt_num"], attempt)
                self.assertEqual(decoded["payload"], payload)

    def test_packet_has_header_and_payload(self):
        packet = encode_message(
            TASK_DISPATCH,
            task_id=25,
            worker_id=7,
            attempt_num=1,
            payload=DISPATCH_PAYLOAD,
        )

        self.assertEqual(len(packet), HEADER_SIZE + len(DISPATCH_PAYLOAD))

    def test_empty_payload_checksum_is_zero(self):
        packet = encode_message(WORKER_JOIN)

        decoded = decode_message(packet)

        self.assertEqual(decoded["payload"], b"")

        checksum = struct.unpack("!I", packet[12:16])[0]
        self.assertEqual(checksum, 0)

    def test_checksum_is_calculated_over_payload_only(self):
        packet = encode_message(
            TASK_DISPATCH,
            task_id=25,
            worker_id=7,
            attempt_num=1,
            payload=DISPATCH_PAYLOAD,
        )

        stored_checksum = struct.unpack("!I", packet[12:16])[0]
        expected_checksum = zlib.crc32(DISPATCH_PAYLOAD) & 0xFFFFFFFF

        self.assertEqual(stored_checksum, expected_checksum)

    def test_maximum_header_field_values(self):
        """The header should support maximum unsigned field values."""

        packet = encode_message(
            TASK_DISPATCH,
            task_id=0xFFFFFFFF,
            worker_id=0xFFFF,
            attempt_num=0xFFFF,
            payload=DISPATCH_PAYLOAD,
        )

        decoded = decode_message(packet)

        self.assertEqual(decoded["task_id"], 0xFFFFFFFF)
        self.assertEqual(decoded["worker_id"], 0xFFFF)
        self.assertEqual(decoded["attempt_num"], 0xFFFF)

    def test_minimum_valid_ids_for_task_messages(self):
        """Task_ID, Worker_ID and Attempt_Num may all be exactly 1."""

        messages = [
            (TASK_DISPATCH, DISPATCH_PAYLOAD),
            (TASK_RESULT, RESULT_PAYLOAD),
            (ACK_RESULT, b""),
        ]

        for msg_type, payload in messages:
            with self.subTest(message_type=msg_type):
                packet = encode_message(
                    msg_type,
                    task_id=1,
                    worker_id=1,
                    attempt_num=1,
                    payload=payload,
                )

                decoded = decode_message(packet)

                self.assertEqual(decoded["task_id"], 1)
                self.assertEqual(decoded["worker_id"], 1)
                self.assertEqual(decoded["attempt_num"], 1)

    def test_heartbeat_and_accept_with_minimum_worker_id(self):
        for msg_type in (HEARTBEAT, WORKER_ACCEPT):
            with self.subTest(message_type=msg_type):
                packet = encode_message(msg_type, worker_id=1)
                self.assertEqual(decode_message(packet)["worker_id"], 1)


# ==========================================
# 3. Header validation tests
# ==========================================

class TestHeaderValidation(unittest.TestCase):

    # ---------- WORKER_JOIN ----------

    def test_valid_worker_join(self):
        packet = encode_message(WORKER_JOIN)
        decoded = decode_message(packet)

        self.assertEqual(decoded["message_type"], WORKER_JOIN)

    def test_invalid_worker_join_with_worker_id(self):
        with self.assertRaises(ValueError):
            encode_message(WORKER_JOIN, worker_id=5)

    def test_invalid_worker_join_with_task_id(self):
        with self.assertRaises(ValueError):
            encode_message(WORKER_JOIN, task_id=10)

    def test_invalid_worker_join_with_attempt_number(self):
        with self.assertRaises(ValueError):
            encode_message(WORKER_JOIN, attempt_num=1)

    # ---------- HEARTBEAT ----------

    def test_valid_heartbeat(self):
        packet = encode_message(
            HEARTBEAT,
            worker_id=5,
        )

        decoded = decode_message(packet)

        self.assertEqual(decoded["worker_id"], 5)

    def test_invalid_heartbeat_without_worker_id(self):
        with self.assertRaises(ValueError):
            encode_message(HEARTBEAT)

    def test_invalid_heartbeat_with_task_id(self):
        with self.assertRaises(ValueError):
            encode_message(
                HEARTBEAT,
                task_id=10,
                worker_id=5,
            )

    def test_invalid_heartbeat_with_attempt_number(self):
        with self.assertRaises(ValueError):
            encode_message(
                HEARTBEAT,
                worker_id=5,
                attempt_num=1,
            )

    # ---------- TASK_DISPATCH ----------

    def test_valid_task_dispatch_header(self):
        packet = encode_message(
            TASK_DISPATCH,
            task_id=10,
            worker_id=5,
            attempt_num=1,
            payload=DISPATCH_PAYLOAD,
        )

        self.assertEqual(
            decode_message(packet)["message_type"],
            TASK_DISPATCH,
        )

    def test_invalid_task_dispatch_without_task_id(self):
        with self.assertRaises(ValueError):
            encode_message(
                TASK_DISPATCH,
                worker_id=5,
                attempt_num=1,
                payload=DISPATCH_PAYLOAD,
            )

    def test_invalid_task_dispatch_without_worker_id(self):
        with self.assertRaises(ValueError):
            encode_message(
                TASK_DISPATCH,
                task_id=10,
                attempt_num=1,
                payload=DISPATCH_PAYLOAD,
            )

    def test_invalid_task_dispatch_without_attempt_number(self):
        with self.assertRaises(ValueError):
            encode_message(
                TASK_DISPATCH,
                task_id=10,
                worker_id=5,
                attempt_num=0,
                payload=DISPATCH_PAYLOAD,
            )

    # ---------- TASK_RESULT ----------

    def test_valid_task_result_header(self):
        packet = encode_message(
            TASK_RESULT,
            task_id=10,
            worker_id=5,
            attempt_num=2,
            payload=RESULT_PAYLOAD,
        )

        decoded = decode_message(packet)

        self.assertEqual(decoded["message_type"], TASK_RESULT)
        self.assertEqual(decoded["attempt_num"], 2)

    def test_invalid_task_result_without_task_id(self):
        with self.assertRaises(ValueError):
            encode_message(
                TASK_RESULT,
                worker_id=5,
                attempt_num=1,
                payload=RESULT_PAYLOAD,
            )

    def test_invalid_task_result_attempt_number(self):
        with self.assertRaises(ValueError):
            encode_message(
                TASK_RESULT,
                task_id=10,
                worker_id=5,
                attempt_num=0,
                payload=RESULT_PAYLOAD,
            )

    def test_invalid_task_result_without_worker_id(self):
        with self.assertRaises(ValueError):
            encode_message(
                TASK_RESULT,
                task_id=10,
                attempt_num=1,
                payload=RESULT_PAYLOAD,
            )

    # ---------- ACK_RESULT ----------

    def test_valid_ack_result_header(self):
        packet = encode_message(
            ACK_RESULT,
            task_id=10,
            worker_id=5,
            attempt_num=3,
        )

        decoded = decode_message(packet)

        self.assertEqual(decoded["message_type"], ACK_RESULT)
        self.assertEqual(decoded["task_id"], 10)
        self.assertEqual(decoded["attempt_num"], 3)

    def test_invalid_ack_result_without_worker_id(self):
        with self.assertRaises(ValueError):
            encode_message(
                ACK_RESULT,
                task_id=10,
                attempt_num=1,
            )

    def test_invalid_ack_result_without_task_id(self):
        with self.assertRaises(ValueError):
            encode_message(
                ACK_RESULT,
                worker_id=5,
                attempt_num=1,
            )

    def test_invalid_ack_result_without_attempt_number(self):
        with self.assertRaises(ValueError):
            encode_message(
                ACK_RESULT,
                task_id=10,
                worker_id=5,
                attempt_num=0,
            )

    # ---------- WORKER_ACCEPT ----------

    def test_valid_worker_accept(self):
        packet = encode_message(
            WORKER_ACCEPT,
            worker_id=5,
        )

        decoded = decode_message(packet)

        self.assertEqual(decoded["message_type"], WORKER_ACCEPT)
        self.assertEqual(decoded["worker_id"], 5)

    def test_invalid_worker_accept_without_worker_id(self):
        with self.assertRaises(ValueError):
            encode_message(WORKER_ACCEPT)

    def test_invalid_worker_accept_with_task_id(self):
        with self.assertRaises(ValueError):
            encode_message(
                WORKER_ACCEPT,
                task_id=10,
                worker_id=5,
            )

    def test_invalid_worker_accept_with_attempt_number(self):
        with self.assertRaises(ValueError):
            encode_message(
                WORKER_ACCEPT,
                worker_id=5,
                attempt_num=1,
            )

    # ---------- unknown type ----------

    def test_unknown_message_type_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_header_fields(99, 0, 0, 0)

    # ---------- all invalid combinations, one table ----------

    def test_every_invalid_header_combination_is_rejected_by_encode(self):
        for msg_type, task_id, worker_id, attempt, payload in INVALID_HEADERS:
            with self.subTest(
                message_type=msg_type,
                task_id=task_id,
                worker_id=worker_id,
                attempt_num=attempt,
            ):
                with self.assertRaises(ValueError):
                    encode_message(
                        msg_type,
                        task_id,
                        worker_id,
                        attempt,
                        payload,
                    )

    def test_validate_header_fields_accepts_valid_combinations(self):
        for msg_type, task_id, worker_id, attempt, _ in VALID_MESSAGES:
            with self.subTest(message_type=msg_type):
                # Returns None and raises nothing for a valid header.
                self.assertIsNone(
                    validate_header_fields(
                        msg_type, task_id, worker_id, attempt
                    )
                )

    def test_validate_header_fields_rejects_every_invalid_combination(self):
        for msg_type, task_id, worker_id, attempt, _ in INVALID_HEADERS:
            with self.subTest(
                message_type=msg_type,
                task_id=task_id,
                worker_id=worker_id,
                attempt_num=attempt,
            ):
                with self.assertRaises(ValueError):
                    validate_header_fields(
                        msg_type, task_id, worker_id, attempt
                    )

    # ---------- negative attempt numbers ----------

    def test_negative_attempt_number_is_rejected_for_every_type(self):
        """
        A negative attempt number violates the semantic rules of every
        message type, so it is rejected with ValueError before struct
        packing is ever reached.
        """

        cases = [
            (WORKER_JOIN, 0, 0, b""),
            (HEARTBEAT, 0, 5, b""),
            (TASK_DISPATCH, 10, 5, DISPATCH_PAYLOAD),
            (TASK_RESULT, 10, 5, RESULT_PAYLOAD),
            (ACK_RESULT, 10, 5, b""),
            (WORKER_ACCEPT, 0, 5, b""),
        ]

        for msg_type, task_id, worker_id, payload in cases:
            with self.subTest(message_type=msg_type):
                with self.assertRaises(ValueError):
                    encode_message(
                        msg_type,
                        task_id,
                        worker_id,
                        -1,
                        payload,
                    )

    # ---------- negative / oversized IDs on otherwise valid messages ----------

    def test_negative_task_id_is_rejected_on_task_messages(self):
        """
        Negative Task_ID is not zero, so the field rules accept it and
        struct.pack rejects it (struct.error).
        """

        cases = [
            (TASK_DISPATCH, DISPATCH_PAYLOAD),
            (TASK_RESULT, RESULT_PAYLOAD),
            (ACK_RESULT, b""),
        ]

        for msg_type, payload in cases:
            with self.subTest(message_type=msg_type):
                with self.assertRaises(struct.error):
                    encode_message(
                        msg_type,
                        task_id=-1,
                        worker_id=5,
                        attempt_num=1,
                        payload=payload,
                    )

    def test_negative_worker_id_is_rejected_on_worker_messages(self):
        cases = [
            (HEARTBEAT, 0, 0, b""),
            (TASK_DISPATCH, 10, 1, DISPATCH_PAYLOAD),
            (TASK_RESULT, 10, 1, RESULT_PAYLOAD),
            (ACK_RESULT, 10, 1, b""),
            (WORKER_ACCEPT, 0, 0, b""),
        ]

        for msg_type, task_id, attempt, payload in cases:
            with self.subTest(message_type=msg_type):
                with self.assertRaises(struct.error):
                    encode_message(
                        msg_type,
                        task_id,
                        -1,
                        attempt,
                        payload,
                    )

    def test_task_id_overflow_is_rejected(self):
        with self.assertRaises(struct.error):
            encode_message(
                TASK_DISPATCH,
                task_id=0x100000000,
                worker_id=5,
                attempt_num=1,
                payload=DISPATCH_PAYLOAD,
            )

    def test_attempt_number_overflow_is_rejected(self):
        with self.assertRaises(struct.error):
            encode_message(
                TASK_RESULT,
                task_id=10,
                worker_id=5,
                attempt_num=65536,
                payload=RESULT_PAYLOAD,
            )


# ==========================================
# 4. TASK_DISPATCH payload tests
# ==========================================

class TestTaskDispatchPayload(unittest.TestCase):

    def test_normal_task_dispatch(self):
        payload = encode_task_dispatch(0, 100, 50)

        self.assertEqual(len(payload), 12)

        decoded = decode_task_dispatch(payload)

        self.assertEqual(decoded["start"], 0)
        self.assertEqual(decoded["end"], 100)
        self.assertEqual(decoded["target"], 50)

    def test_boundary_values(self):
        payload = encode_task_dispatch(
            0,
            0xFFFFFFFF,
            0xFFFFFFFF,
        )

        decoded = decode_task_dispatch(payload)

        self.assertEqual(decoded["start"], 0)
        self.assertEqual(decoded["end"], 0xFFFFFFFF)
        self.assertEqual(decoded["target"], 0xFFFFFFFF)

    def test_start_equal_to_end_is_rejected(self):
        with self.assertRaises(ValueError):
            encode_task_dispatch(10, 10, 5)

    def test_start_greater_than_end_is_rejected(self):
        with self.assertRaises(ValueError):
            encode_task_dispatch(20, 10, 5)

    def test_negative_number_is_rejected(self):
        with self.assertRaises(struct.error):
            encode_task_dispatch(-1, 10, 5)

    def test_integer_overflow_is_rejected(self):
        with self.assertRaises(struct.error):
            encode_task_dispatch(0, 0x100000000, 5)

    def test_wrong_payload_size_is_rejected(self):
        with self.assertRaises(ValueError):
            decode_task_dispatch(b"\x00" * 11)

    def test_invalid_range_received_from_packet_is_rejected(self):
        invalid_payload = struct.pack("!III", 10, 10, 5)

        with self.assertRaises(ValueError):
            decode_task_dispatch(invalid_payload)

    def test_non_bytes_payload_is_rejected(self):
        with self.assertRaises(TypeError):
            decode_task_dispatch("not bytes")


# ==========================================
# 5. TASK_RESULT payload tests
# ==========================================

class TestTaskResultPayload(unittest.TestCase):

    def test_success_result(self):
        payload = encode_task_result(SUCCESS, 50)

        self.assertEqual(len(payload), 5)

        decoded = decode_task_result(payload)

        self.assertEqual(decoded["status"], SUCCESS)
        self.assertEqual(decoded["result"], 50)

    def test_not_found_result(self):
        payload = encode_task_result(NOT_FOUND, 0)

        decoded = decode_task_result(payload)

        self.assertEqual(decoded["status"], NOT_FOUND)
        self.assertEqual(decoded["result"], 0)

    def test_error_result(self):
        payload = encode_task_result(ERROR, 1)

        decoded = decode_task_result(payload)

        self.assertEqual(decoded["status"], ERROR)
        self.assertEqual(decoded["result"], 1)

    def test_invalid_status_cannot_be_encoded(self):
        with self.assertRaises(ValueError):
            encode_task_result(99, 50)

    def test_invalid_status_is_rejected_when_decoding(self):
        invalid_payload = struct.pack("!BI", 99, 50)

        with self.assertRaises(ValueError):
            decode_task_result(invalid_payload)

    def test_wrong_result_payload_size_is_rejected(self):
        with self.assertRaises(ValueError):
            decode_task_result(b"\x00" * 4)

    def test_result_integer_overflow_is_rejected(self):
        with self.assertRaises(struct.error):
            encode_task_result(SUCCESS, 0x100000000)

    def test_negative_result_is_rejected(self):
        with self.assertRaises(struct.error):
            encode_task_result(SUCCESS, -1)

    def test_non_bytes_payload_is_rejected(self):
        with self.assertRaises(TypeError):
            decode_task_result("not bytes")


# ==========================================
# 6. Complete packet validation tests
# ==========================================

class TestPacketValidation(unittest.TestCase):

    def setUp(self):
        self.valid_packet = encode_message(
            TASK_DISPATCH,
            task_id=25,
            worker_id=7,
            attempt_num=1,
            payload=DISPATCH_PAYLOAD,
        )

    def test_packet_shorter_than_header_is_rejected(self):
        with self.assertRaises(ValueError):
            decode_message(b"\x00" * 15)

    def test_packet_larger_than_limit_is_rejected(self):
        oversized_packet = b"\x00" * 513

        with self.assertRaises(ValueError):
            decode_message(oversized_packet)

    def test_corrupted_payload_is_rejected(self):
        corrupted = bytearray(self.valid_packet)

        # Change one payload byte.
        corrupted[-1] ^= 0x01

        with self.assertRaises(ValueError):
            decode_message(bytes(corrupted))

    def test_unsupported_version_is_rejected(self):
        corrupted = bytearray(self.valid_packet)

        # Version is at offset 0.
        corrupted[0] = 2

        with self.assertRaises(ValueError):
            decode_message(bytes(corrupted))

    def test_unknown_message_type_is_rejected(self):
        corrupted = bytearray(self.valid_packet)

        # Message Type is at offset 1.
        corrupted[1] = 99

        with self.assertRaises(ValueError):
            decode_message(bytes(corrupted))

    def test_payload_length_mismatch_is_rejected(self):
        corrupted = bytearray(self.valid_packet)

        # Payload Length occupies offsets 10 and 11.
        corrupted[10:12] = struct.pack("!H", 13)

        with self.assertRaises(ValueError):
            decode_message(bytes(corrupted))

    def test_extra_payload_on_empty_message_is_rejected(self):
        packet = encode_message(WORKER_JOIN)
        packet += b"\x01"

        with self.assertRaises(ValueError):
            decode_message(packet)

    def test_extra_byte_is_rejected_for_every_message_type(self):
        for msg_type, task_id, worker_id, attempt, payload in VALID_MESSAGES:
            with self.subTest(message_type=msg_type):
                packet = encode_message(
                    msg_type, task_id, worker_id, attempt, payload
                )

                with self.assertRaises(ValueError):
                    decode_message(packet + b"\x00")

    def test_truncated_packet_is_rejected_for_every_message_type(self):
        """Every proper prefix of a valid packet must be rejected."""

        for msg_type, task_id, worker_id, attempt, payload in VALID_MESSAGES:
            packet = encode_message(
                msg_type, task_id, worker_id, attempt, payload
            )

            for cut in range(len(packet)):
                with self.subTest(message_type=msg_type, length=cut):
                    with self.assertRaises(ValueError):
                        decode_message(packet[:cut])

    def test_invalid_payload_size_for_message_type_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_payload(TASK_DISPATCH, b"\x00" * 11)

    def test_unknown_message_type_in_payload_validation(self):
        with self.assertRaises(ValueError):
            validate_payload(99, b"")

    def test_non_bytes_packet_is_rejected(self):
        with self.assertRaises(TypeError):
            decode_message("not a packet")

    def test_bytearray_packet_is_rejected(self):
        """Only bytes are accepted; callers must convert bytearray."""

        with self.assertRaises(TypeError):
            decode_message(bytearray(self.valid_packet))

    def test_non_bytes_payload_is_rejected(self):
        with self.assertRaises(TypeError):
            encode_message(WORKER_JOIN, payload="not bytes")

    def test_bytearray_payload_is_rejected(self):
        with self.assertRaises(TypeError):
            encode_message(WORKER_JOIN, payload=bytearray(b""))

    def test_invalid_header_integer_range_is_rejected(self):
        with self.assertRaises(struct.error):
            encode_message(
                HEARTBEAT,
                worker_id=65536,
            )

    def test_invalid_header_semantics_in_received_packet(self):
        """
        Create a packet with a structurally valid header but invalid
        WORKER_JOIN fields. Decoding should reject it.
        """

        invalid_header = struct.pack(
            HEADER_FORMAT,
            PROTOCOL_VERSION,
            WORKER_JOIN,
            10,  # Invalid Task_ID for WORKER_JOIN
            0,
            0,
            0,
            0,
        )

        with self.assertRaises(ValueError):
            decode_message(invalid_header)

    def test_invalid_header_semantics_rejected_on_decode_for_every_type(self):
        """
        The decoder must apply the per-message-type field rules to
        packets built by a misbehaving sender, for all six message types.
        """

        for msg_type, task_id, worker_id, attempt, payload in INVALID_HEADERS:
            with self.subTest(
                message_type=msg_type,
                task_id=task_id,
                worker_id=worker_id,
                attempt_num=attempt,
            ):
                raw = build_raw_packet(
                    msg_type, task_id, worker_id, attempt, payload
                )

                with self.assertRaises(ValueError):
                    decode_message(raw)

    def test_raw_builder_produces_decodable_packet_when_header_is_valid(self):
        """
        Sanity check for the test helper itself: with valid field values
        the raw builder output must decode, so the rejections above are
        really caused by the header rules.
        """

        for msg_type, task_id, worker_id, attempt, payload in VALID_MESSAGES:
            with self.subTest(message_type=msg_type):
                raw = build_raw_packet(
                    msg_type, task_id, worker_id, attempt, payload
                )

                self.assertEqual(
                    raw,
                    encode_message(
                        msg_type, task_id, worker_id, attempt, payload
                    ),
                )
                self.assertEqual(
                    decode_message(raw)["message_type"], msg_type
                )


# ==========================================
# 7. Structure vs payload meaning
# ==========================================

class TestStructureVersusPayloadMeaning(unittest.TestCase):
    """
    decode_message() checks the packet STRUCTURE (version, type, header
    rules, length, size, checksum). It does not interpret the payload.
    Payload meaning is checked by decode_task_dispatch() and
    decode_task_result(), so callers must use those too.

    These tests document that behaviour. If the team later moves payload
    checks into decode_message(), update them.
    """

    def test_dispatch_with_invalid_range_passes_structural_decode(self):
        bad_payload = struct.pack("!III", 10, 10, 5)  # start == end

        raw = build_raw_packet(TASK_DISPATCH, 10, 5, 1, bad_payload)

        decoded = decode_message(raw)  # structurally valid

        with self.assertRaises(ValueError):
            decode_task_dispatch(decoded["payload"])

    def test_result_with_invalid_status_passes_structural_decode(self):
        bad_payload = struct.pack("!BI", 99, 50)  # status 99 is undefined

        raw = build_raw_packet(TASK_RESULT, 10, 5, 1, bad_payload)

        decoded = decode_message(raw)  # structurally valid

        with self.assertRaises(ValueError):
            decode_task_result(decoded["payload"])

    def test_full_receive_path_for_a_valid_dispatch(self):
        packet = encode_message(
            TASK_DISPATCH,
            task_id=25,
            worker_id=7,
            attempt_num=2,
            payload=encode_task_dispatch(1000, 2000, 1234),
        )

        decoded = decode_message(packet)
        task = decode_task_dispatch(decoded["payload"])

        self.assertEqual(decoded["task_id"], 25)
        self.assertEqual(decoded["attempt_num"], 2)
        self.assertEqual(task["start"], 1000)
        self.assertEqual(task["end"], 2000)
        self.assertEqual(task["target"], 1234)

    def test_full_receive_path_for_a_valid_result(self):
        packet = encode_message(
            TASK_RESULT,
            task_id=25,
            worker_id=7,
            attempt_num=2,
            payload=encode_task_result(SUCCESS, 1234),
        )

        decoded = decode_message(packet)
        result = decode_task_result(decoded["payload"])

        self.assertEqual(result["status"], SUCCESS)
        self.assertEqual(result["result"], 1234)


# ==========================================
# 8. Decoder robustness (receive-loop safety)
# ==========================================

class TestDecoderRobustness(unittest.TestCase):
    """
    A server/worker receive loop that catches only ValueError must never
    see any other exception type from decode_message() when it is given
    bytes. These tests feed it damaged and random input and check that
    the only possible outcomes are a decoded dict or ValueError.

    They deliberately do NOT require every damaged packet to be rejected
    (the checksum covers the payload only); they require that the decoder
    never crashes with an unexpected exception.
    """

    def _assert_decodes_or_raises_value_error(self, data):
        try:
            result = decode_message(data)
        except ValueError:
            return

        self.assertIsInstance(result, dict)

    def test_every_single_bit_flip_never_crashes_the_decoder(self):
        for msg_type, task_id, worker_id, attempt, payload in VALID_MESSAGES:
            packet = encode_message(
                msg_type, task_id, worker_id, attempt, payload
            )

            for index in range(len(packet)):
                for bit in range(8):
                    mutated = bytearray(packet)
                    mutated[index] ^= 1 << bit

                    with self.subTest(
                        message_type=msg_type, byte=index, bit=bit
                    ):
                        self._assert_decodes_or_raises_value_error(
                            bytes(mutated)
                        )

    def test_random_garbage_never_crashes_the_decoder(self):
        rng = random.Random(12345)  # fixed seed: reproducible

        for trial in range(500):
            length = rng.randint(0, 600)
            data = bytes(rng.getrandbits(8) for _ in range(length))

            with self.subTest(trial=trial, length=length):
                self._assert_decodes_or_raises_value_error(data)

    def test_random_header_values_never_crash_the_decoder(self):
        """
        Headers with the right version and a correct CRC but random
        field values must be accepted or rejected cleanly.
        """

        rng = random.Random(2024)

        for trial in range(500):
            msg_type = rng.randint(0, 10)
            task_id = rng.choice([0, 1, rng.getrandbits(32)])
            worker_id = rng.choice([0, 1, rng.getrandbits(16)])
            attempt = rng.choice([0, 1, rng.getrandbits(16)])
            payload = bytes(
                rng.getrandbits(8) for _ in range(rng.choice([0, 5, 12]))
            )

            raw = build_raw_packet(
                msg_type, task_id, worker_id, attempt, payload
            )

            with self.subTest(trial=trial, message_type=msg_type):
                self._assert_decodes_or_raises_value_error(raw)


# ==========================================
# 9. Run tests
# ==========================================

if __name__ == "__main__":
    unittest.main(verbosity=2)
