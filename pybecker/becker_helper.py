import logging
import re
import time
import threading
import queue
from typing import Any, Callable, Tuple
import os
import sys
import serial
import serial.tools.list_ports

STX = b'\x02'
ETX = b'\x03'

CODE_PREFIX = "0000000002010B"  # 0-23 (24 chars)
CODE_SUFFIX = "000000"
CODE_21 = "021"
CODE_REMOTE = "01"  # centronic remote control used "02" while contralControl seem to use "01"

DEFAULT_DEVICE_NAME = '/dev/serial/by-id/usb-BECKER-ANTRIEBE_GmbH_CDC_RS232_v125_Centronic-if00'

MESSAGE = re.compile(
      STX
    + CODE_PREFIX.encode()
    + rb'[0-9A-F]{4,4}'
    + CODE_SUFFIX.encode()
    + rb'(?P<unit_id>[0-9A-F]{5,5})'
    + rb'[0-9A-F]{6,6}'
    + rb'(?P<channel>[0-9A-F]{1,1})'
    + rb'00'
    + rb'(?P<command>[124]{1,1})'            # HALT, UP, DOWN
    + rb'(?P<argument>[0-9A-F]{1,1})'
    + rb'[0-9A-F]{2,2}'
    + ETX, re.I
)

COMMANDS = {b'1': 'HALT', b'2': 'UP', b'4': 'DOWN'}

_LOGGER = logging.getLogger(__name__)


def hex2(n):
    return '%02X' % (n & 0xFF)


def hex4(n):
    return '%04X' % (n & 0xFFFF)


def checksum(code):
    code_length = len(code)
    if code_length != 40:
        _LOGGER.error("The code must be 40 characters long (without <STX>, <ETX> and checksum)")
        return
    code_sum = 0
    i = 0
    while i < code_length:
        hex_code = code[i] + code[i + 1]
        code_sum += int(hex_code, 16)
        i += 2
    return '%s%s' % (code.upper(), hex2(0x03 - code_sum))


def generate_code(channel, unit, cmd_code, with_checksum=True):
    unit_id = unit[0]  # contains the unit code in hex (5 chars)
    unit_inc = unit[1]  # contains the next increment (required to convert into hex4)

    if channel == 0:
        # channel 0 may be used for wall mounted sender (primary used as master sender)
        code = CODE_PREFIX + hex4(unit_inc) + CODE_SUFFIX + unit_id + CODE_21 + "00" + hex2(channel) + '00' + hex2(
            cmd_code)
    else:
        code = CODE_PREFIX + hex4(unit_inc) + CODE_SUFFIX + unit_id + CODE_21 + CODE_REMOTE + hex2(channel) + '00' \
               + hex2(cmd_code)
    return checksum(code) if with_checksum else code

def finalize_code(code):
    return b"".join([STX, code.encode(), ETX])


class BeckerConnectionError(Exception):
    pass


class BeckerConnection():
    """
    Connection class for Becker centronic USB Stick.
    """
    def __init__(self, device: str) -> None:
        """Initialize connection."""
        self._device, self._is_serial = self._validate_device(device)
        try:
            self._connection = serial.serial_for_url(
                self.device,
                baudrate=115200,
                timeout=0,
                do_not_open = True
            )
        except serial.SerialException as err:
            raise BeckerConnectionError(
                "Error when trying to establish connection using {}.".format(self.device)
            ) from err
        self._open()

    @property
    def is_serial(self) -> bool:
        """Return if device is serial port."""
        return self._is_serial

    @property
    def device(self) -> str:
        """Return device name."""
        return self._device

    def write(self, packet: bytes) -> None:
        """Write data."""
        self._open()
        try:
            self._connection.write(packet)
        except serial.SerialException:
            if self._is_serial:
                raise
            # Re-connect on error
            _LOGGER.debug("Write failed. Try to close and re-open connection to %s", self.device)
            self._connection.close()
            self._open()
            self._connection.write(packet)

    def read(self) -> bytes:
        """Read data."""
        packet = bytes()
        self._open()
        try:
            packet = self._connection.read(1024)
        except serial.SerialException:
            if self._is_serial:
                raise
            # Re-connect on error
            _LOGGER.debug("Read failed. Try to close and re-open connection to %s", self.device)
            self._connection.close()
        return packet

    def _open(self) -> None:
        if not self._connection.is_open:
            _LOGGER.debug("Try to open connection.")
            try:
                self._connection.open()
            except serial.SerialException as err:
                if self.is_serial:
                    raise BeckerConnectionError(
                        "Error when trying to establish connection using {}.".format(self.device)
                    ) from err
                _LOGGER.error("Establish connection to %s failed!", self.device)
            except:     # pylint: disable=bare-except
                _LOGGER.error("Establish connection to %s failed!", self.device)

    def close(self) -> None:
        """Close connection"""
        if self._connection.is_open:
            self._connection.close()

    @staticmethod
    def _validate_device(device: str) -> Tuple[str, bool]:
        """Validate device name."""
        is_serial = False
        is_socket = True
        if device is None:
            device = DEFAULT_DEVICE_NAME
        if "/dev/" in device:
            if not os.path.exists(device):
                raise BeckerConnectionError("{} is not existing".format(device))
            is_serial = True
            is_socket = False
        elif sys.platform.startswith('win') and 'COM' in device.upper():
            if not device.upper() in [i.device for i in serial.tools.list_ports.comports()]:
                raise BeckerConnectionError("{} is not existing".format(device))
            is_serial = True
            is_socket = False
        elif "/" in device:
            is_socket = False
        if is_socket:
            if ':' in device:
                host, port = device.split(':', 1)
            else:
                host = device
                port = '5000'
            device = f'socket://{host}:{port}'
        return device, is_serial


class BeckerCommunicator(threading.Thread):
    """
    Communicator class for Becker centronic USB Stick.
    """
    def __init__(
        self,
        device: str,
        callback: Callable[[re.Match], Any] = None,
        deamon: bool = True,
    ) -> None:
        '''Initialize communicator'''
        super().__init__(daemon=deamon)
        # Setup threading stop event and queue
        self._stop_flag = threading.Event()
        self._write_queue = queue.Queue(maxsize=100)
        # Setup callback
        self._callback = callback
        # Setup interface
        self._connection = BeckerConnection(device=device)
        self._read_buffer = bytes()

    def run(self) -> None:
        '''Run BeckerCommunicator thread.'''
        _LOGGER.debug('BeckerCommunicator thread started.')
        callback_valid = False if self._callback is None else True    # pylint: disable=simplifiable-if-expression
        packet = None
        while True:
            # Get packet from write queue
            try:
                packet = self._write_queue.get(block=False)
            except queue.Empty:
                pass
            else:
                self._connection.write(packet)
                self._log(packet, "Sent packet: ")
            # Read bytes from serial port
            if callback_valid:
                self._read_buffer += self._connection.read()
                self._parse()
            # Sleep for thread switch and wait time between packets
            time.sleep(0.01)
            # Ensure all packets in queue are send before thread is stopped
            if self._stop_flag.is_set() and self._write_queue.empty():
                break
        _LOGGER.debug('BeckerCommunicator thread stopped.')

    def stop(self) -> None:
        '''Stop BeckerCommunicator thread.'''
        self._stop_flag.set()

    def _parse(self) -> None:
        """Parse received packets and run callback."""
        end = 0
        for data in MESSAGE.finditer(self._read_buffer):
            self._log(data.group(0), "Received packet: ")
            self._callback(data)
            end = data.end()
        self._read_buffer = self._read_buffer[end:]

    def _log(self, packet: bytes, text: str = "") -> None:
        """Log packets."""
        if _LOGGER.getEffectiveLevel() <= logging.DEBUG:
            match = MESSAGE.search(packet)
            if match is not None:
                if match.group('command') in COMMANDS:
                    command = COMMANDS[match.group('command')]
                else:
                    command = match.group('command').decode()
                _LOGGER.debug(
                    "%sunit_id: %s, channel: %s, command: %s, argument: %s, packet: %s",
                    text,
                    match.group('unit_id').decode(),
                    match.group('channel').decode(),
                    command,
                    match.group('argument').decode(),
                    match.group(0),
                )

    def send(self, packet) -> None:
        """Send packet."""
        if not self.is_alive():
            raise BeckerConnectionError(
                "Error BeckerCommunicator thread not alive."
            )
        try:
            self._write_queue.put(packet, timeout=5)
        except queue.Full as err:
            self.stop()
            raise BeckerConnectionError(
                "Error sending packet. BeckerCommunicator thread not responding."
            ) from err

    def close(self) -> None:
        """Stop thread and close device"""
        self.stop()
        self.join(timeout=5)
        self._connection.close()
