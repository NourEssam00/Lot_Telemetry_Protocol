# sensor2.py
import socket
import struct
import time
import random
import argparse
from sensor_base import TelemetrySensor

class HumiditySensor(TelemetrySensor):
    def __init__(self, server_ip="127.0.0.1", server_port=9000, device_id=1002, 
                 report_interval=1.0, batch_size=3, heartbeat_interval=15):
        super().__init__(server_ip, server_port, device_id, report_interval, 
                        batch_size, heartbeat_interval)
    
    def generate_reading(self):
        """Generate humidity reading in hundredths of percent"""
        return random.randint(2000, 8000)  # 20.00% to 80.00%

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Humidity Sensor')
    parser.add_argument("--host", default="127.0.0.1", help="Server IP address")
    parser.add_argument("--port", type=int, default=9000, help="Server port")
    parser.add_argument("--id", type=int, default=1002, help="Device ID")
    parser.add_argument("--interval", type=float, default=1.0, 
                       help="Reporting interval in seconds (1, 5, or 30)")
    parser.add_argument("--batch", type=int, default=3, 
                       help="Batch size (number of readings per packet)")
    parser.add_argument("--heartbeat", type=float, default=15.0,
                       help="Heartbeat interval in seconds")
    parser.add_argument("--duration", type=float, default=60,
                       help="Test duration in seconds")
    parser.add_argument("--continuous", action="store_true",
                       help="Run continuously instead of fixed duration")
    
    args = parser.parse_args()
    
    if args.interval not in [1, 5, 30]:
        print(f"Warning: Interval {args.interval}s not in [1, 5, 30]. Using anyway.")
    
    sensor = HumiditySensor(
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