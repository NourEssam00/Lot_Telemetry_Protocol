#!/bin/bash
python3 sensors/sensor2.py --duration 60 &
python3 sensors/sensor3.py --duration 60 &
wait
