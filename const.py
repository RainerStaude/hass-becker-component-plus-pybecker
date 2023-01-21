"""Becker Cover Constants."""

import re

from homeassistant.const import (
    STATE_CLOSED,
    STATE_OPEN,
)

from .pybecker.becker import (
    COMMAND_HALT,
    COMMAND_UP,
    COMMAND_UP5,
    COMMAND_DOWN,
    COMMAND_DOWN5,
    COMMAND_RELEASE,
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
CONF_INTERMEDIATE_DISABLE = 'intermediate_position_disable'         # deprecated
CONF_INTERMEDIATE_POSITION = 'intermediate_position'
CONF_INTERMEDIATE_POSITION_UP = 'intermediate_position_up'
CONF_INTERMEDIATE_POSITION_DOWN = 'intermediate_position_down'
CONF_TILT_INTERMEDIATE = 'tilt_intermediate'
CONF_TILT_BLIND = 'tilt_blind'
CONF_TILT_TIME_BLIND = 'tilt_time_blind'

TILT_FUNCTIONALITY = 'tilt_functionality'

CLOSED_POSITION = 0
VENTILATION_POSITION = 25
INTERMEDIATE_POSITION = 75
OPEN_POSITION = 100
TILT_TIME = 0.3
TILT_RECEIVE_TIMEOUT = 1.0

COMMANDS = {
    'halt': f'{COMMAND_HALT:02x}'.encode(),
    'up': f'{COMMAND_UP:02x}'.encode(),
    'up_intermediate': f'{COMMAND_UP5:02x}'.encode(),
    'down': f'{COMMAND_DOWN:02x}'.encode(),
    'down_intermediate': f'{COMMAND_DOWN5:02x}'.encode(),
    'release': f'{COMMAND_RELEASE:02x}'.encode(),
}

REMOTE_ID = re.compile(r'(?P<id>[0-9A-F]{5,5}):(?P<ch>[0-9A-F]{1,1})')

TEMPLATE_VALID_OPEN = [STATE_OPEN, 'true', True]
TEMPLATE_VALID_CLOSE = [STATE_CLOSED, 'false', False]
TEMPLATE_UNKNOWN_STATES = ['unknown', 'unavailable', 'none', None]
