#Registers workers, assigns IDs, and tracks heartbeats.
import time

HEARTBEAT_TIMEOUT = 6


class WorkerManager:

    def __init__(self):
        self.workers = {}
        self.next_worker_id = 1

    # Register a new worker or return its existing ID
    def register_worker(self, address):

        for worker_id, worker in self.workers.items():

            if worker["address"] == address:

                worker["last_heartbeat"] = time.time()
                worker["status"] = "ACTIVE"

                print(f"Worker {worker_id} already registered.")

                return worker_id

        worker_id = self.next_worker_id
        self.next_worker_id += 1

        self.workers[worker_id] = {
            "address": address,
            "status": "ACTIVE",
            "last_heartbeat": time.time()
        }

        print(f"Worker {worker_id} registered.")

        return worker_id

    # Update the heartbeat of a registered worker
    def update_heartbeat(self, worker_id, address):

        if worker_id not in self.workers:
            return False

        if self.workers[worker_id]["address"] != address:
            return False

        self.workers[worker_id]["last_heartbeat"] = time.time()
        self.workers[worker_id]["status"] = "ACTIVE"

        return True

    # Detect inactive workers
    def check_inactive_workers(self):

        current_time = time.time()

        for worker_id, worker in self.workers.items():

            elapsed = current_time - worker["last_heartbeat"]

            if elapsed > HEARTBEAT_TIMEOUT:

                if worker["status"] != "INACTIVE":
                    worker["status"] = "INACTIVE"
                    print(f"Worker {worker_id} is now INACTIVE.")

    # Return all registered workers
    def get_workers(self):

        return self.workers
