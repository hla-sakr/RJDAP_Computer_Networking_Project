import socket
import sys
import os

# Import protocol.py from the parent folder
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

import protocol


SERVER_ADDRESS = ("127.0.0.1", 2006)

# Create UDP socket
worker_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
worker_socket.settimeout(5)


try:

    # STEP 1: Register worker

    join_packet = protocol.encode_message(
        message_type=protocol.WORKER_JOIN
    )

    worker_socket.sendto(join_packet, SERVER_ADDRESS)

    print("WORKER_JOIN sent.")

    # Receive registration confirmation
    packet, server_address = worker_socket.recvfrom(512)

    message = protocol.decode_message(packet)

    if message["message_type"] != protocol.WORKER_ACCEPT:
        raise ValueError("Expected WORKER_ACCEPT.")

    worker_id = message["worker_id"]

    print("WORKER_ACCEPT received!")
    print("Assigned Worker ID:", worker_id)


    # STEP 2: Send heartbeat

    heartbeat_packet = protocol.encode_message(
        message_type=protocol.HEARTBEAT,
        worker_id=worker_id
    )

    worker_socket.sendto(heartbeat_packet, SERVER_ADDRESS)

    print("HEARTBEAT sent.")


    # STEP 3: Receive task from server

    packet, server_address = worker_socket.recvfrom(512)

    message = protocol.decode_message(packet)

    if message["message_type"] != protocol.TASK_DISPATCH:
        raise ValueError("Expected TASK_DISPATCH.")

    print("\nTASK_DISPATCH received!")

    task_id = message["task_id"]
    attempt_num = message["attempt_num"]

    # Decode task information
    task = protocol.decode_task_dispatch(message["payload"])

    start = task["start"]
    end = task["end"]

    print("Task ID:", task_id)
    print("Task range:", start, "to", end)


    # STEP 4: Execute task

    result = sum(range(start, end + 1))

    print("\nTask completed!")
    print("Computed Result:", result)


    # STEP 5: Send result to server

    result_payload = protocol.encode_task_result(
        status=1,       # SUCCESS
        result=result
    )

    result_packet = protocol.encode_message(
        message_type=protocol.TASK_RESULT,
        task_id=task_id,
        worker_id=worker_id,
        attempt_num=attempt_num,
        payload=result_payload
    )

    worker_socket.sendto(result_packet, SERVER_ADDRESS)

    print("\nTASK_RESULT sent to server.")


    # STEP 6: Receive ACK_RESULT

    packet, server_address = worker_socket.recvfrom(512)

    message = protocol.decode_message(packet)

    if message["message_type"] == protocol.ACK_RESULT:

        print("ACK_RESULT received!")
        print("Task", message["task_id"], "successfully acknowledged.")

    else:

        print("Unexpected response received.")


    # STEP 7: Test invalid packet handling

    invalid_packet = b"INVALID_PACKET"

    worker_socket.sendto(invalid_packet, SERVER_ADDRESS)

    print("\nInvalid packet sent.")


except socket.timeout:

    print("Server did not respond within the expected time.")

except (ValueError, TypeError) as error:

    print("Communication error:", error)

finally:

    worker_socket.close()
    print("\nWorker socket closed.")
