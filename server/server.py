import socket
import sys
import os

# Allow importing protocol.py from the project root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import protocol

from worker_manager import WorkerManager


# Server configuration
SERVER_IP = "127.0.0.1"
SERVER_PORT = 2006

BUFFER_SIZE = protocol.MAX_PACKET_SIZE


def start_server():

    # Create UDP socket
    server_socket = socket.socket(
        socket.AF_INET,
        socket.SOCK_DGRAM
    )

    # Bind socket to IP address and port
    server_socket.bind((SERVER_IP, SERVER_PORT))

    # Set timeout so the server periodically checks worker status
    server_socket.settimeout(1)

    # Create worker manager
    worker_manager = WorkerManager()

    print("RJDAP Server started.")
    print(f"Listening on {SERVER_IP}:{SERVER_PORT}")

    try:

        while True:

            try:

                # Receive packet from a worker
                packet, worker_address = server_socket.recvfrom(BUFFER_SIZE)

                # Decode and validate packet
                message = protocol.decode_message(packet)

                message_type = message["message_type"]

                # Handle worker registration
                if message_type == protocol.WORKER_JOIN:

                    handle_worker_join(
                        server_socket,
                        worker_manager,
                        worker_address
                    )

                # Handle heartbeat
                elif message_type == protocol.HEARTBEAT:

                    handle_heartbeat(
                        worker_manager,
                        message,
                        worker_address
                    )

                # Handle task result
                elif message_type == protocol.TASK_RESULT:

                    handle_task_result(
                        server_socket,
                        worker_manager,
                        message,
                        worker_address
                    )

                else:

                    print(
                        f"Unexpected message type {message_type} "
                        f"from {worker_address}"
                    )

            except socket.timeout:
                pass

            except (ValueError, TypeError) as error:

                print(f"Invalid packet received: {error}")

            # Check for inactive workers
            worker_manager.check_inactive_workers()

    except KeyboardInterrupt:

        print("\nServer shutting down.")

    finally:

        server_socket.close()


# STEP 1: Handle WORKER_JOIN
def handle_worker_join(server_socket, worker_manager, worker_address):

    print(f"\nWORKER_JOIN received from {worker_address}")

    # Register worker and obtain its ID
    worker_id = worker_manager.register_worker(worker_address)

    # Construct WORKER_ACCEPT packet
    response = protocol.encode_message(
        message_type=protocol.WORKER_ACCEPT,
        task_id=0,
        worker_id=worker_id,
        attempt_num=0,
        payload=b""
    )

    # Send registration confirmation
    server_socket.sendto(response, worker_address)

    print(f"WORKER_ACCEPT sent. Assigned Worker ID: {worker_id}")

    # STEP 2: Send a simple task to the worker

    task_id = 1

    # Encode task information
    task_payload = protocol.encode_task_dispatch(
        start=1,
        end=100,
        target=0
    )

    # Construct TASK_DISPATCH packet
    task_packet = protocol.encode_message(
        message_type=protocol.TASK_DISPATCH,
        task_id=task_id,
        worker_id=worker_id,
        attempt_num=1,
        payload=task_payload
    )

    # Send task to worker
    server_socket.sendto(task_packet, worker_address)

    print(f"TASK_DISPATCH sent to Worker {worker_id}")


# STEP 3: Handle HEARTBEAT
def handle_heartbeat(worker_manager, message, worker_address):

    worker_id = message["worker_id"]

    success = worker_manager.update_heartbeat(
        worker_id,
        worker_address
    )

    if success:

        print(f"Heartbeat received from Worker {worker_id}")

    else:

        print(
            f"Heartbeat rejected: unknown worker or "
            f"address mismatch ({worker_address})"
        )


# STEP 4: Handle TASK_RESULT and send ACK_RESULT
def handle_task_result(server_socket, worker_manager, message, worker_address):

    worker_id = message["worker_id"]

    # Verify that the result came from the registered worker
    workers = worker_manager.get_workers()

    if worker_id not in workers or workers[worker_id]["address"] != worker_address:

        print(f"TASK_RESULT rejected from {worker_address}")
        return

    # Decode result payload
    result_data = protocol.decode_task_result(message["payload"])

    task_id = message["task_id"]
    result = result_data["result"]
    status = result_data["status"]

    print(f"\nTASK_RESULT received from Worker {worker_id}")
    print(f"Task ID: {task_id}")

    if status == 1:
        print("Task Status: SUCCESS")
    else:
        print(f"Task Status: {status}")

    print(f"Computed Result: {result}")

    # Construct ACK_RESULT packet
    ack_packet = protocol.encode_message(
        message_type=protocol.ACK_RESULT,
        task_id=task_id,
        worker_id=worker_id,
        attempt_num=message["attempt_num"],
        payload=b""
    )

    # Send acknowledgement to worker
    server_socket.sendto(ack_packet, worker_address)

    print(f"ACK_RESULT sent to Worker {worker_id}")


if __name__ == "__main__":
    start_server()
