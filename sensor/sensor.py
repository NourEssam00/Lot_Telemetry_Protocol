# sensor1.py
import socket
import struct
import time
import random
import argparse
from sensor_base import TelemetrySensor

ACK_TIMEOUT = 2.0  # seconds
MAX_RETRIES = 3
HIGH_TEMP_THRESHOLD = 3500  # 35.00°C

class TemperatureSensor(TelemetrySensor):
    def __init__(self, server_ip="127.0.0.1", server_port=9000, device_id=1001, 
                 report_interval=1.0, batch_size=3, heartbeat_interval=15):
        super().__init__(server_ip, server_port, device_id, report_interval, 
                        batch_size, heartbeat_interval)
        self.sock.settimeout(ACK_TIMEOUT)

    def generate_reading(self):
        """Generate temperature reading in hundredths of degrees Celsius"""
        return random.randint(1500, 3500)  # 15.00°C to 40.00°C

    def send_batch_packet(self):
        """Send batch and handle ACK if any reading >= HIGH_TEMP_THRESHOLD"""
        if len(self.batch_buffer) < self.batch_size:
            return False

        payload = b''.join([struct.pack("!I", v) for v in self.batch_buffer])
        flags = 0x02 if any(v >= HIGH_TEMP_THRESHOLD for v in self.batch_buffer) else 0x00
        pkt = self.build_packet(1, payload, flags)

        need_ack = any(v >= HIGH_TEMP_THRESHOLD for v in self.batch_buffer)

        if need_ack:
            retries = 0
            ack_received = False
            while retries < MAX_RETRIES and not ack_received:
                self.sock.sendto(pkt, (self.server_ip, self.server_port))
                print(f"Sensor {self.device_id} -> BATCH DATA #{self.seq} (values={self.batch_buffer}) [awaiting ACK]")
                try:
                    data, _ = self.sock.recvfrom(1024)
                    if data.startswith(b"ACK"):
                        ack_seq = int(data[4:])
                        if ack_seq == self.seq:
                            ack_received = True
                            print(f"Sensor {self.device_id}: ACK received for seq #{self.seq}")
                except socket.timeout:
                    retries += 1
                    print(f"Sensor {self.device_id}: No ACK, retry {retries}/{MAX_RETRIES}")
        else:
            self.sock.sendto(pkt, (self.server_ip, self.server_port))
            print(f"Sensor {self.device_id} -> BATCH DATA #{self.seq} (values={self.batch_buffer})")

        self.last_data_time = time.time()
        self.batch_buffer = []
        return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Temperature Sensor with ACK handling')
    parser.add_argument("--host", default="127.0.0.1", help="Server IP address")
    parser.add_argument("--port", type=int, default=9000, help="Server port")
    parser.add_argument("--id", type=int, default=1001, help="Device ID")
    parser.add_argument("--interval", type=float, default=1.0, help="Reporting interval in seconds")
    parser.add_argument("--batch", type=int, default=3, help="Batch size")
    parser.add_argument("--heartbeat", type=float, default=15.0, help="Heartbeat interval")
    parser.add_argument("--duration", type=float, default=60, help="Test duration")
    parser.add_argument("--continuous", action="store_true", help="Run continuously")
    
    args = parser.parse_args()
    
    sensor = TemperatureSensor(
        server_ip=args.host,
        server_port=args.port,
        device_id=args.id,
        report_interval=args.interval,
        batch_size=args.batch,
        heartbeat_interval=args.heartbeat
    )
    
    if args.continuous:
        sensor.run_continuous()
    else:
        sensor.run(duration=args.duration)