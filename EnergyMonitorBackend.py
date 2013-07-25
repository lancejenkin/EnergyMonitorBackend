__author__ = 'lancejenkin'
from collections import namedtuple
import sqlite3
import smbus
import os
import time

SMBUS_PORT = 1 # I2C port
ADDRESS = 0x17 # Address of EnergyMonitor slave
DB_FILE = os.path.join(os.path.realpath(__file__), "database.sqlite")

# Position in state byte of the meter box's LED state
PEAK = 0
OFF_PEAK = 2
TOTAL = 1

LdrIndex = namedtuple("LdrIndex", ["name", "index"])
LDR_INDICES = (LdrIndex("peak", PEAK), LdrIndex("off peak", OFF_PEAK), LdrIndex("total", TOTAL))


def initialise_state(bus, address):
    # Initialise the EnergyMonitor, tell it to read the state
    bus.wrte_byte(address, 0x01)


def read_state(bus, address):
    # Reads the state of the LDR
    # returns the result as a 3-tuple

    state_byte = bus.read_byte(address)
    if state_byte == 0xFF:
        # Data wasn't ready
        return None

    # Convert useful information from byte to tuple
    state = ((state_byte & (1 << PEAK) >> PEAK),
             (state_byte & (1 << OFF_PEAK) >> OFF_PEAK),
             (state_byte & (1 << TOTAL) >> TOTAL))

    return state


def initialize_database():
    # Initialize the database for capturing LDR state changes
    db = sqlite3.connect(DB_FILE)
    cursor = db.cursor()

    cursor.execute("""CREATE TABLE IF NOT EXISTS 'state_readings'
        ('id' INTERGER PRIMARY KEY AUTOINCREMENT,
        'meter_box' VARCHAR,
        'utc_timestamp' INTEGER,
        'energy_usage' REAL)""")

    db.commit()

    return db


def state_change(db, meter_box, timestamp, energy_usage):
    # Store the state change in the database
    cursor = db.cursor()

    cursor.execute("""INSERT INTO state_readings
        (meter_box, utc_timestamp, energy_usage) VALUES (?, ?, ?)""",
                   (meter_box, timestamp, energy_usage))
    db.commit()


def determine_usage(timestamp, last_timestamp):
    # Determine the current energy usage
    # A state change represents 1 Watt . Hour
    # Therefore 1 * 60 * 60 / (timestamp - last_timestamp) = current usage in watts

    return 60 * 60 / (timestamp - last_timestamp)


def get_timestamp():
    # Return milliseconds since epoch
    return int((time.time() + 0.5) * 1000)


def main():
    # Main method
    db = initialize_database()
    last_ldr_states = None
    bus = smbus.SMBus(SMBUS_PORT)
    # The timestamp of the last ldr state change
    last_state_timestamps = [None] * len(LDR_INDICES)
    while True:
        initialise_state(bus, ADDRESS)
        time.sleep(0.1)
        ldr_states = read_state(bus, ADDRESS)

        if last_ldr_states is None:
            last_ldr_states = ldr_states
        else:
            # We need at least one stage change to be able
            # to determine the current energy usage
            for loop_index, ldr_index in enumerate(LDR_INDICES):
                if last_ldr_states[ldr_index.index] != ldr_states[loop_index]:
                    # State change
                    current_timestamp = get_timestamp()
                    if last_state_timestamps[loop_index] is not None:
                        last_timestamp = last_state_timestamps[loop_index]
                        usage = determine_usage(current_timestamp, last_timestamp)
                        state_change(ldr_index.name, current_timestamp, usage)

                    last_state_timestamps[loop_index] = current_timestamp



if __name__=="__main__":
    main()
