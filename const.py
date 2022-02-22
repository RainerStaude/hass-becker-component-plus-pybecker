"""Becker Cover Constants."""

import re

from .pybecker.becker import (
    COMMAND_HALT,
    COMMAND_UP,
    COMMAND_UP5,
    COMMAND_DOWN,
    COMMAND_DOWN5,
)

DOMAIN = "becker"
MANUFACTURER = "Becker"

DEVICE = "device"
DEVICE_CLASS = "shutter"

RECEIVE_MESSAGE = "receive_message"

CONF_CHANNEL = "channel"
CONF_COVERS = "covers"
CONF_UNIT = "unit"
CONF_REMOTE_ID = "remote_id"
CONF_TRAVELLING_TIME_DOWN = 'travelling_time_down'
CONF_TRAVELLING_TIME_UP = 'travelling_time_up'
CONF_INTERMEDIATE_DISABLE = 'intermediate_position_disable'
CONF_INTERMEDIATE_POSITION_UP = 'intermediate_position_up'
CONF_INTERMEDIATE_POSITION_DOWN = 'intermediate_position_down'

CLOSED_POSITION = 0
VENTILATION_POSITION = 25
INTERMEDIATE_POSITION = 75
OPEN_POSITION = 100

COMMANDS = {
    'halt': f'{COMMAND_HALT:02x}'.encode(),
    'up': f'{COMMAND_UP:02x}'.encode(),
    'up_intermediate': f'{COMMAND_UP5:02x}'.encode(),
    'down': f'{COMMAND_DOWN:02x}'.encode(),
    'down_intermediate': f'{COMMAND_DOWN5:02x}'.encode(),
}

REMOTE_ID = re.compile(r'(?P<id>[0-9A-F]{5,5}):(?P<ch>[0-9A-F]{1,1})')
