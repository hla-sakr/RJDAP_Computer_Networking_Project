

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
    encode_task_dispatch,
    decode_task_dispatch,
    encode_task_result,
    decode_task_result,
)


class TestProtocolConstants(unittest.TestCase):

    def test_header_is_exactly_16_bytes(self):
        self.assertEqual(HEADER_SIZE, 16)
        self.assertEqual(struct.calcsize(HEADER_FORMAT), 16)

    def test_packet_size_limit(self):
        self.assertEqual(MAX_PACKET_SIZE, 512)
        self.assertEqual(MAX_PAYLOAD_SIZE, 496)

    def test_protocol_version(self):
        self.assertEqual(PROTOCOL_VERSION, 1)


class TestMessageEncoding(unittest.TestCase):

    def test_all_message_types_round_trip(self):
        """Every supported message type should encode and decode."""

        messages = [
            (WORKER_JOIN, 0, 0, 0, b""),
            (HEARTBEAT, 0, 7, 0, b""),
            (
                TASK_DISPATCH,
                25,
                7,
                1,
                encode_task_dispatch(0, 100, 50),
            ),
            (
                TASK_RESULT,
                25,
                7,
                1,
                encode_task_result(SUCCESS, 50),
            ),
            (ACK_RESULT, 25, 7, 1, b""),
            (WORKER_ACCEPT, 0, 7, 0, b""),
        ]

        for msg_type, task_id, worker_id, attempt, payload in messages:
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
        payload = encode_task_dispatch(0, 100, 50)

        packet = encode_message(
            TASK_DISPATCH,
            task_id=25,
            worker_id=7,
            attempt_num=1,
            payload=payload,
        )

        self.assertEqual(len(packet), HEADER_SIZE + len(payload))

    def test_empty_payload_checksum_is_zero(self):
        packet = encode_message(WORKER_JOIN)

        decoded = decode_message(packet)

        self.assertEqual(decoded["payload"], b"")
        self.assertEqual(
            struct.unpack("!I", packet[12:16])[0],
            0,
        )

    def test_checksum_is_calculated_over_payload_only(self):
        payload = encode_task_dispatch(0, 100, 50)
        packet = encode_message(TASK_DISPATCH, payload=payload)

        stored_checksum = struct.unpack("!I", packet[12:16])[0]
        expected_checksum = zlib.crc32(payload) & 0xFFFFFFFF

        self.assertEqual(stored_checksum, expected_checksum)

    def test_maximum_header_field_values(self):
        """The header should support the largest unsigned field values."""

        packet = encode_message(
            WORKER_JOIN,
            task_id=0xFFFFFFFF,
            worker_id=0xFFFF,
            attempt_num=0xFFFF,
        )

        decoded = decode_message(packet)

        self.assertEqual(decoded["task_id"], 0xFFFFFFFF)
        self.assertEqual(decoded["worker_id"], 0xFFFF)
        self.assertEqual(decoded["attempt_num"], 0xFFFF)


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


class TestPacketValidation(unittest.TestCase):

    def setUp(self):
        payload = encode_task_dispatch(0, 100, 50)

        self.valid_packet = encode_message(
            TASK_DISPATCH,
            task_id=25,
            worker_id=7,
            attempt_num=1,
            payload=payload,
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

    def test_invalid_payload_size_for_message_type_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_payload(TASK_DISPATCH, b"\x00" * 11)

    def test_unknown_message_type_in_payload_validation(self):
        with self.assertRaises(ValueError):
            validate_payload(99, b"")

    def test_non_bytes_packet_is_rejected(self):
        with self.assertRaises(TypeError):
            decode_message("not a packet")

    def test_non_bytes_payload_is_rejected(self):
        with self.assertRaises(TypeError):
            encode_message(WORKER_JOIN, payload="not bytes")

    def test_invalid_header_integer_range_is_rejected(self):
        with self.assertRaises(struct.error):
            encode_message(
                WORKER_JOIN,
                worker_id=65536,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
