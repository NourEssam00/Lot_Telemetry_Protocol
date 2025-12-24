# server_oop.py
import socket
import struct
import csv
import time
import os
import threading
from queue import Queue
import psutil
import statistics
from datetime import datetime

# Global CSV lock
csv_lock = threading.Lock()
# Global queue to store incoming packets
packet_queue = Queue()
# Global metrics storage
metrics = {
    'total_packets': 0,
    'total_readings': 0,
    'duplicate_count': 0,
    'gap_count': 0,
    'total_bytes': 0,
    'cpu_times': [],
    'start_time': None
}
metrics_lock = threading.Lock()

def write_metrics_to_file(metrics, filename="metrics_summary.txt"):
    with open(filename, "w") as f:
        f.write("=== Metrics Summary ===\n")
        for key, value in metrics.items():
            f.write(f"{key}: {value}\n")

class TelemetryServer:
    HEADER_FMT = "!B H H I B"
    HEADER_SIZE = struct.calcsize(HEADER_FMT)

    def __init__(self, host="0.0.0.0", port=9000):
        self.host = host
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.last_seq = {}
        self.duplicate_counts = {}
        self.gap_counts = {}
        self.reorder_buffer = {}
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.host, self.port))
        
        # Initialize metrics
        with metrics_lock:
            metrics['start_time'] = time.time()
        
        # Heartbeat tracking
        self.device_heartbeats = {}  # store heartbeat timestamps per device
        self.device_status = {}      # ONLINE / OFFLINE
        self.last_values = {}        # store last readings per device
        self.status_csv = "device_status.csv"
        with open(self.status_csv, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["device_id", "timestamp", "status"])  # CSV header
        
        print(f"Server listening on {self.host}:{self.port}\n")

    def run(self):
        self.init_logging()
        # Start worker thread to process packets from queue
        worker = threading.Thread(target=self.queue_worker, daemon=True)
        worker.start()

        while True:
            data, addr = self.sock.recvfrom(4096)
            packet_queue.put((data, addr))

    def queue_worker(self):
        while True:
            data, addr = packet_queue.get()
            try:
                self.handle_packet_threadsafe(data, addr)
            finally:
                packet_queue.task_done()

    def handle_packet_threadsafe(self, data, addr):
        start_cpu = time.perf_counter()
        self.handle_packet(data, addr)
        end_cpu = time.perf_counter()
        with metrics_lock:
            metrics['cpu_times'].append((end_cpu - start_cpu) * 1000)  # Convert to ms

    def handle_packet(self, data, addr):
        if len(data) < self.HEADER_SIZE:
            print("Invalid protocol: packet too short")
            return

        header = data[:self.HEADER_SIZE]
        payload = data[self.HEADER_SIZE:]

        try:
            raw_byte, device_id, seq, timestamp, flags = struct.unpack(self.HEADER_FMT, header)
            version = (raw_byte >> 4) & 0x0F
            msg_type = raw_byte & 0x0F
        except Exception as e:
            print("Error unpacking header:", e)
            return

        # Metrics
        with metrics_lock:
            metrics['total_packets'] += 1
            metrics['total_bytes'] += len(data)

        arrival_ts = time.time()
        arrival_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(arrival_ts))
        sent_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))

        print(f"Received Packet from {addr} at {arrival_str}")
        print(f"  version={version}, type={msg_type}, id={device_id}, seq={seq}, sent={sent_str}, flags=0x{flags:02X}")

        duplicate_flag, gap_flag, gap_count_here = self.detect_seq_state(device_id, seq)

        if duplicate_flag:
            print(f"Duplicate packet from device {device_id}, seq {seq}")
            return

        # Handle gap / packet loss
        if gap_flag:
            print(f"Gap detected for device {device_id}: {gap_count_here} packets missing")
            if device_id in self.last_values:
                predicted_values = self.last_values[device_id]
                print(f"Predicted missing values for device {device_id}: {predicted_values}")
            with metrics_lock:
                metrics['gap_count'] += gap_count_here

        # Process messages
        reading_count = 0 

        if msg_type == 1:  # DATA
            values = self.parse_values(payload)
            reading_count = len(values)
            # save last values
            self.last_values[device_id] = values

            with metrics_lock:
                metrics['total_readings'] += reading_count

            print(f"Device {device_id} values: {values}")

            # Send ACK if sensor requested (flag 0x01)
            if flags & 0x02:
                self.send_ack(addr, device_id, seq)

        elif msg_type == 2:  # HEARTBEAT
            self.handle_heartbeat(device_id)
        else:
            print(f"Unknown message type {msg_type} from device {device_id}")
            return

        # Store in reorder buffer
        if device_id not in self.reorder_buffer:
            self.reorder_buffer[device_id] = []
        self.reorder_buffer[device_id].append(
            (timestamp, device_id, seq, msg_type, payload, duplicate_flag, gap_flag, flags, reading_count)
        )
        if len(self.reorder_buffer[device_id]) >= 5:
            self.flush_reordered(device_id)

        print()

    def send_ack(self, addr, device_id, seq):
        msg = f"ACK {seq}".encode()
        self.sock.sendto(msg, addr)
        print(f"Sent ACK to device {device_id} for seq {seq}")

    def detect_seq_state(self, device_id, seq):
        duplicate_flag = 0
        gap_flag = 0
        gap_count_here = 0

        last = self.last_seq.get(device_id)
        if last is None:
            self.last_seq[device_id] = seq
            self.duplicate_counts[device_id] = 0
            self.gap_counts[device_id] = 0
            return duplicate_flag, gap_flag, gap_count_here

        if seq == last:
            duplicate_flag = 1
            self.duplicate_counts[device_id] += 1
            with metrics_lock:
                metrics['duplicate_count'] += 1
        elif seq == (last + 1) & 0xFFFF:
            self.last_seq[device_id] = seq
        elif (seq & 0xFFFF) > (last & 0xFFFF) and seq > last + 1:
            gap_flag = 1
            gap_count_here = seq - last - 1
            self.gap_counts[device_id] += gap_count_here
            self.last_seq[device_id] = seq
        else:
            print(f"Out-of-order packet from device {device_id}: seq {seq} < last {last}")

        return duplicate_flag, gap_flag, gap_count_here

    def parse_values(self, payload):
        if len(payload) == 0:
            return []
        values = []
        for i in range(0, len(payload), 4):
            chunk = payload[i:i+4]
            if len(chunk) < 4:
                continue
            values.append(struct.unpack("!I", chunk)[0])
        return values

    def handle_heartbeat(self, device_id):
        current_time = time.time()
        last_times = self.device_heartbeats.get(device_id, [])
        last_times.append(current_time)
        self.device_heartbeats[device_id] = last_times[-10:]

        # calculate dynamic interval
        if len(last_times) >= 2:
            intervals = [t2 - t1 for t1, t2 in zip(last_times[:-1], last_times[1:])]
            avg_interval = sum(intervals) / len(intervals)
        else:
            avg_interval = 1.0

        # ONLINE/OFFLINE status
        prev_status = self.device_status.get(device_id, "ONLINE")
        if prev_status == "ONLINE" and len(last_times) >= 2 and (current_time - last_times[-2]) > 2 * avg_interval:
            status = "OFFLINE"
        else:
            status = "ONLINE"

        if prev_status != status or device_id not in self.device_status:
            self.device_status[device_id] = status
            with csv_lock:
                with open(self.status_csv, "a", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow([device_id, int(current_time), status])
            print(f"Device {device_id} status: {status}")

        print(f"  HEARTBEAT received from device {device_id}, interval={avg_interval:.2f}s")

    def init_logging(self):
        self.log_file = "telemetry_log.csv"
        file_exists = os.path.isfile(self.log_file)
        with open(self.log_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "device_id", "seq", "msg_type", "timestamp_sent",
                "timestamp_arrival", "duplicate_flag", "gap_flag", "flags", "payload_value"
            ])

    def flush_reordered(self, device_id):
        self.reorder_buffer[device_id].sort(key=lambda x: x[0])
        with csv_lock:
            for ts, dev_id, seq, msg_type, payload, duplicate_flag, gap_flag, flags, reading_count in self.reorder_buffer[device_id]:
                arrival_time = int(time.time())
                if msg_type == 1:
                    values = self.parse_values(payload)
                    value = values
                else:
                    value = "HEARTBEAT"

                if not duplicate_flag:
                    with open(self.log_file, "a", newline="") as f:
                        writer = csv.writer(f)
                        writer.writerow([dev_id, seq, msg_type, ts, arrival_time, duplicate_flag, gap_flag, flags, value])
        self.reorder_buffer[device_id].clear()

    def calculate_metrics(self):
        with metrics_lock:
            if metrics['total_packets'] == 0:
                return None
            total_time = time.time() - metrics['start_time']
            bytes_per_report = metrics['total_bytes'] / max(metrics['total_readings'], 1)
            duplicate_rate = metrics['duplicate_count'] / max(metrics['total_packets'], 1)
            avg_cpu_ms = statistics.mean(metrics['cpu_times']) if metrics['cpu_times'] else 0
            return {
                'bytes_per_report': round(bytes_per_report, 2),
                'packets_received': metrics['total_packets'],
                'duplicate_rate': round(duplicate_rate * 100, 2),
                'sequence_gap_count': metrics['gap_count'],
                'cpu_ms_per_report': round(avg_cpu_ms, 3),
                'total_readings': metrics['total_readings'],
                'total_bytes': metrics['total_bytes'],
                'test_duration_seconds': round(total_time, 2)
            }

if __name__ == "__main__":
    import signal
    import sys

    server = TelemetryServer()

    def signal_handler(sig, frame):
        print("\n\n=== Test Complete - Metrics Summary ===")
        metrics_summary = server.calculate_metrics()
        if metrics_summary:
            print(f"Bytes per report: {metrics_summary['bytes_per_report']}")
            print(f"Packets received: {metrics_summary['packets_received']}")
            print(f"Duplicate rate: {metrics_summary['duplicate_rate']}%")
            print(f"Sequence gap count: {metrics_summary['sequence_gap_count']}")
            print(f"CPU ms per report: {metrics_summary['cpu_ms_per_report']}")
            print(f"Total readings: {metrics_summary['total_readings']}")
            print(f"Test duration: {metrics_summary['test_duration_seconds']}s")
        write_metrics_to_file(metrics_summary)
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    server.run()