__author__ = 'lancejenkin'
from collections import namedtuple
import sqlite3
import pymysql
import smbus
import os
import sys
import time

SMBUS_PORT = 1 # I2C port
ADDRESS = 0x17 # Address of EnergyMonitor slave

MYSQL_HOST = "10.0.0.6"
MYSQL_USER = "lance"
MYSQL_PASS = "lance"
MYSQL_DB = "energy_monitor"

# Position in state byte of the meter box's LED state
PHASE_1 = 0
PHASE_2 = 1
PHASE_3 = 2

LdrIndex = namedtuple("LdrIndex", ["name", "index"])
LDR_INDICES = (LdrIndex("phase 1", PHASE_1), LdrIndex("phase 2", PHASE_2), LdrIndex("phase 3", PHASE_3))


def initialise_state(bus, address):
    # Initialise the EnergyMonitor, tell it to read the state
    try:
        bus.write_byte(address, 0x01)
    except:
        # Error writing state
        pass


def read_state(bus, address):
    # Reads the state of the LDR
    # returns the result as a 3-tuple
    try:
        state_byte = bus.read_byte(address)
    except:
        # Error reading state
        state_byte = 0xFF

    if state_byte == 0xFF:
        # Data wasn't ready
        return None

    # Convert useful information from byte to tuple
    state = (((state_byte & (1 << PHASE_1)) >> PHASE_1),
             ((state_byte & (1 << PHASE_2)) >> PHASE_2),
             ((state_byte & (1 << PHASE_3)) >> PHASE_3))

    return state


def initialize_database():
    # Initialize the database for capturing LDR state changes
    db = pymysql.connect(MYSQL_HOST, MYSQL_USER, MYSQL_PASS, MYSQL_DB)

    return db


def state_change(db, meter_box, timestamp, energy_usage):
    # Store the state change in the database
    cursor = db.cursor()

    cursor.execute("""INSERT INTO state_readings (`meter_box`,`utc_timestamp`,`energy_usage`) VALUES (%s, %s, %s)""",
                   (meter_box, timestamp, energy_usage))




def determine_usage(timestamp, last_timestamp):
    # Determine the current energy usage
    # A state change represents 1 Watt . Hour
    # Time stamps are in milliseconds
    # Therefore 1000 * 60 * 60 / (timestamp - last_timestamp) = current usage in watts

    return 1000 * 60 * 60 / (timestamp - last_timestamp)


def get_timestamp():
    # Return milliseconds since epoch
    return int((time.time() + 0.5) * 1000)


def main(argv):
    # Main method
    db = initialize_database()
    last_ldr_states = None
    bus = smbus.SMBus(SMBUS_PORT)
    # The timestamp of the last ldr state change
    last_state_timestamps = [None] * len(LDR_INDICES)
    one_change_since_none = False
    while True:
        initialise_state(bus, ADDRESS)
        time.sleep(0.01)
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
                        if one_change_since_none:
                            # We need at least one state change before acurately
                            # determining energy usage
                            last_timestamp = last_state_timestamps[loop_index]
                            usage = determine_usage(current_timestamp, last_timestamp)
                            state_change(db, ldr_index.name, current_timestamp, usage)

                            last_state_timestamps[loop_index] = current_timestamp
                        one_change_since_none = True
                    else:
                        one_change_since_none = False
                        last_state_timestamps[loop_index] = current_timestamp

            last_ldr_states = ldr_states



if __name__=="__main__":
    main(sys.argv)
