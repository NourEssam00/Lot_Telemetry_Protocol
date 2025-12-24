# sensor_base.py
import socket
import struct
import time
import random
import argparse

class TelemetrySensor:
    HEADER_FMT = "!B H H I B"  # matches server
    MAX_PAYLOAD_BYTES = 200 - 10  # 200 bytes max, minus header size (10 bytes)
    MAX_READINGS_PER_BATCH = (MAX_PAYLOAD_BYTES // 4)  # Each reading is 4 bytes
    
    def __init__(self, server_ip="127.0.0.1", server_port=9000, device_id=1001, 
                 report_interval=1.0, batch_size=3, heartbeat_interval=15):
        self.server_ip = server_ip
        self.server_port = server_port
        self.device_id = device_id
        self.report_interval = report_interval
        self.heartbeat_interval = heartbeat_interval
        self.batch_size = min(batch_size, self.MAX_READINGS_PER_BATCH)  # Enforce limit
        self.batch_buffer = []
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.seq = 0
        self.last_heartbeat_time = time.time()
        self.last_data_time = time.time()
        
        print(f"Sensor {device_id} initialized:")
        print(f"  Report interval: {report_interval}s")
        print(f"  Heartbeat interval: {heartbeat_interval}s")
        print(f"  Batch size: {self.batch_size} readings")
        print(f"  Max payload size: {self.MAX_PAYLOAD_BYTES} bytes (excluding header)")

    def build_packet(self, msg_type, payload=b'', flags=0):
        """Build packet with proper header"""
        version = 1 & 0x0F
        msg_type = msg_type & 0x0F
        raw_byte = ((version << 4) | msg_type) & 0xFF
        timestamp = int(time.time())
        self.seq = (self.seq + 1) & 0xFFFF
        header = struct.pack(self.HEADER_FMT, raw_byte, self.device_id, self.seq, timestamp, flags)
        
        # Check payload size
        total_size = len(header) + len(payload)
        if total_size > 200:
            print(f"WARNING: Packet size {total_size} exceeds 200 byte limit!")
        
        return header + payload

    def check_payload_size(self, payload):
        """Check if payload size is within limits"""
        header_size = struct.calcsize(self.HEADER_FMT)
        total_size = header_size + len(payload)
        return total_size <= 200

    def send_batch_packet(self):
        """Send batched readings if buffer is full"""
        if len(self.batch_buffer) < self.batch_size:
            return False  # Not enough readings to send
        
        # Build payload (4-byte unsigned ints per reading)
        payload = b''
        for v in self.batch_buffer:
            payload += struct.pack("!I", v)
        
        # Check payload size
        if not self.check_payload_size(payload):
            print(f"Sensor {self.device_id}: Payload too large! Truncating...")
            # Truncate to fit
            max_readings = self.MAX_READINGS_PER_BATCH
            payload = b''
            self.batch_buffer = self.batch_buffer[:max_readings]
            for v in self.batch_buffer[:max_readings]:
                payload += struct.pack("!I", v)
        
        # Set flags: mark as batched
        flags = 0x01
        
        # Build and send packet
        pkt = self.build_packet(1, payload, flags)
        self.sock.sendto(pkt, (self.server_ip, self.server_port))
        print(f"Sensor {self.device_id} -> BATCH DATA #{self.seq} (values={self.batch_buffer})")
        
        self.last_data_time = time.time()
        self.batch_buffer = []
        return True

    def send_heartbeat(self):
        """Send heartbeat packet"""
        pkt = self.build_packet(2, b'', 0)
        self.sock.sendto(pkt, (self.server_ip, self.server_port))
        print(f"Sensor {self.device_id} -> HEARTBEAT #{self.seq}")
        self.last_heartbeat_time = time.time()

    def generate_reading(self):
        """Abstract method to be implemented by specific sensors"""
        raise NotImplementedError

    def should_send_heartbeat(self):
        """Check if it's time to send heartbeat based on elapsed time"""
        current_time = time.time()
        time_since_last_heartbeat = current_time - self.last_heartbeat_time
        time_since_last_data = current_time - self.last_data_time
        
        # Send heartbeat if: 
        # 1. Heartbeat interval has passed since last heartbeat, AND
        # 2. No data has been sent since last heartbeat (or data interval exceeded)
        return (time_since_last_heartbeat >= self.heartbeat_interval and 
                time_since_last_data >= self.report_interval)

    def run(self, duration=60):
        """Run sensor for specified duration (seconds)"""
        print(f"Sensor {self.device_id} starting... (duration: {duration}s)")
        start_time = time.time()
        end_time = start_time + duration
        
        # Initial delay to stagger start times
        time.sleep(self.device_id % 3)
        
        while time.time() < end_time:
            current_time = time.time()
            
            # Check if we should send heartbeat
            if self.should_send_heartbeat():
                self.send_heartbeat()
                # Sleep until next report interval
                time.sleep(self.report_interval)
                continue
            
            # Generate and buffer reading
            reading = self.generate_reading()
            self.batch_buffer.append(reading)
            
            # Try to send batch
            sent = self.send_batch_packet()
            
            # Calculate sleep time
            sleep_time = self.report_interval - (time.time() - current_time)
            if sleep_time > 0:
                time.sleep(sleep_time)
        
        print(f"Sensor {self.device_id} finished after {duration} seconds")

    def run_continuous(self):
        """Run sensor continuously (for testing)"""
        print(f"Sensor {self.device_id} starting continuous operation...")
        
        # Initial delay to stagger start times
        time.sleep(self.device_id % 3)
        
        while True:
            current_time = time.time()
            
            # Check if we should send heartbeat
            if self.should_send_heartbeat():
                self.send_heartbeat()
                # Sleep until next report interval
                time.sleep(self.report_interval)
                continue
            
            # Generate and buffer reading
            reading = self.generate_reading()
            self.batch_buffer.append(reading)
            
            # Try to send batch
            sent = self.send_batch_packet()
            
            # Calculate sleep time
            sleep_time = self.report_interval - (time.time() - current_time)
            if sleep_time > 0:
                time.sleep(sleep_time)