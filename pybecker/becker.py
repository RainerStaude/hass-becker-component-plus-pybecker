import logging
import re
import time
from random import randrange

from .becker_helper import finalize_code
from .becker_helper import generate_code
from .becker_helper import BeckerCommunicator
from .database import Database

COMMAND_UP = 0x20
COMMAND_UP2 = 0x21  # move up
COMMAND_UP3 = 0x22  # move up
COMMAND_UP4 = 0x23  # move up
COMMAND_UP5 = 0x24  # intermediate position "up"
COMMAND_DOWN = 0x40
COMMAND_DOWN2 = 0x41  # move down
COMMAND_DOWN3 = 0x42  # move down
COMMAND_DOWN4 = 0x43  # move down
COMMAND_DOWN5 = 0x44  # intermediate position "down" (sun protection)
COMMAND_HALT = 0x10
COMMAND_PAIR = 0x80  # pair button press
COMMAND_PAIR2 = 0x81  # pair button pressed for 3 seconds (without releasing)
COMMAND_PAIR3 = 0x82  # pair button pressed for 6 seconds (without releasing)
COMMAND_PAIR4 = 0x83  # pair button pressed for 10 seconds (without releasing)

COMMAND_CLEARPOS = 0x90
COMMAND_CLEARPOS2 = 0x91
COMMAND_CLEARPOS3 = 0x92
COMMAND_CLEARPOS4 = 0x93

# DEFAULT_DEVICE_NAME moved to becker_helper

logging.basicConfig()
_LOGGER = logging.getLogger(__name__)


class Becker:
    """
        Becker Shutter Controller
        =========================

        Use this class to perform operations on your Becker Shutter using a centronic USB Stick
        This class will as well maintain a call increment in an internal database
    """
    def __init__(self, device_name=None, init_dummy=False, db_filename=None, callback=None):
        """
            Create a new instance of the Becker controller

            :param  device_name: The path for the centronic stick (default /dev/serial/by-id/usb-BECKER-ANTRIEBE_GmbH_CDC_RS232_v125_Centronic-if00).
            :param  init_dummy: Boolean that indicate if the database should be initialized with a dummy unit (default False).
            :type device_name: str
            :type init_dummy: bool
        """
        self.communicator = BeckerCommunicator(device_name, callback)
        self.db = Database(db_filename)

        # If no unit is defined create a dummy one
        units = self.db.get_all_units()
        if not units and init_dummy:
            self.db.init_dummy()

        # Start communicator thread
        self.communicator.start()

    def close(self):
        """Stop communicator thread, close device and database"""
        self.communicator.close()
        self.db.conn.close()

    async def write(self, codes):
        for code in codes:
            self.communicator.send(finalize_code(code))
            # Sleep implemented in BeckerCommunicator

    async def run_codes(self, channel, unit, cmd, test):
        if unit[2] == 0 and cmd != "TRAIN":
            _LOGGER.error("The unit %s is not configured", (unit[0]))
            return

        # move up/down dependent on given time
        mt = re.match(r"(DOWN|UP):(\d+)", cmd)

        codes = []
        if cmd == "UP":
            codes.append(generate_code(channel, unit, COMMAND_UP))
        elif cmd == "UP2":
            codes.append(generate_code(channel, unit, COMMAND_UP5))
        elif cmd == "HALT":
            codes.append(generate_code(channel, unit, COMMAND_HALT))
        elif cmd == "DOWN":
            codes.append(generate_code(channel, unit, COMMAND_DOWN))
        elif cmd == "DOWN2":
            codes.append(generate_code(channel, unit, COMMAND_DOWN5))
        elif cmd == "TRAIN":
            codes.append(generate_code(channel, unit, COMMAND_PAIR2))
            unit[1] += 1
            codes.append(generate_code(channel, unit, COMMAND_PAIR2))
            # set unit as configured
            unit[2] = 1
        elif cmd == "CLEARPOS":
            codes.append(generate_code(channel, unit, COMMAND_PAIR))
            unit[1] += 1
            codes.append(generate_code(channel, unit, COMMAND_CLEARPOS))
            unit[1] += 1
            codes.append(generate_code(channel, unit, COMMAND_CLEARPOS2))
            unit[1] += 1
            codes.append(generate_code(channel, unit, COMMAND_CLEARPOS3))
            unit[1] += 1
            codes.append(generate_code(channel, unit, COMMAND_CLEARPOS4))
        elif cmd == "REMOVE":
            codes.append(generate_code(channel, unit, COMMAND_PAIR2))
            unit[1] += 1
            codes.append(generate_code(channel, unit, COMMAND_PAIR2))
            unit[1] += 1
            codes.append(generate_code(channel, unit, COMMAND_PAIR3))
            unit[1] += 1
            codes.append(generate_code(channel, unit, COMMAND_PAIR4))
            unit[2] = 0

        if mt:
            _LOGGER.INFO("Moving %s for %s seconds..." % (mt.group(1), mt.group(2)))
            # move down/up for a specific time
            if mt.group(1) == "UP":
                code = generate_code(channel, unit, COMMAND_UP)
            elif mt.group(1) == "DOWN":
                code = generate_code(channel, unit, COMMAND_DOWN)

            unit[1] += 1
            await self.write([code])

            time.sleep(int(mt.group(2)))

            # stop moving
            code = generate_code(channel, unit, COMMAND_HALT)
            unit[1] += 1
            await self.write([code])
        else:
            unit[1] += 1

        # append the release button code
        #codes.append(generate_code(channel, unit, 0))
        #unit[1] += 1

        await self.write(codes)
        self.db.set_unit(unit, test)

    async def send(self, channel, cmd, test=False):

        un, ch = self._split_channel(channel)

        if not 1 <= ch <= 7 and ch != 15:
            _LOGGER.error("Channel must be in range of 1-7 or 15")
            return

        # device check implemented in BeckerCommunicator

        if un > 0:
            unit = self.db.get_unit(un)
            await self.run_codes(ch, unit, cmd, test)
        else:
            units = self.db.get_all_units()
            for unit in units:
                await self.run_codes(ch, unit, cmd, test)

    async def move_up(self, channel):
        """
            Send the command to move up for a given channel.

            :param channel: the channel on which the shutter is listening
            :type channel: str
        """
        await self.send(channel, "UP")

    async def move_up_intermediate(self, channel):
        """
            Send the command to move up in the intermediate position for a given channel.

            :param channel: the channel on which the shutter is listening
            :type channel: str
        """
        await self.send(channel, "UP2")

    async def move_down(self, channel):
        """
            Sent the command to move down for a given channel.

            :param channel: the channel on which the shutter is listening
            :type channel: str
        """
        await self.send(channel, "DOWN")

    async def move_down_intermediate(self, channel):
        """
            Send the command to move down in the intermediate position for a given channel.

            :param channel: the channel on which the shutter is listening
            :type channel: str
        """
        await self.send(channel, "DOWN2")

    async def stop(self, channel):
        """
            Send the command to stop for a given channel.

            :param channel: the channel on which the shutter is listening
            :type channel: str
        """
        await self.send(channel, "HALT")

    async def pair(self, channel):
        """
            Initiate the pairing for a given channel.

            :param channel: the channel on which the shutter is listening
            :type channel: str
        """
        await self.send(channel, "TRAIN")

    async def list_units(self):
        """
        Return all configured units as a list.
        """

        return self.db.get_all_units()

    @staticmethod
    def _split_channel(channel):
        b = channel.split(':')
        if len(b) > 1:
            ch = int(b[1])
            un = int(b[0])
        else:
            ch = int(channel)
            un = 1
        return un, ch

    async def init_unconfigured_unit(self, channel, name=None):
        """Init unconfigured units in database and send init call"""
        # check if unit is configured
        un, ch = self._split_channel(channel)   # pylint: disable=unused-variable
        unit = self.db.get_unit(un)
        if unit[2] == 0:
            _LOGGER.warning(
                "Unit %s%s with channel %s not registered in database file %s!",
                un,
                " of " + name if name is not None else "",
                channel,
                self.db.filename,
            )
            # set the unit as configured
            unit[1] = randrange(10, 40, 1)
            unit[2] = 1
            self.db.set_unit(unit)
            # send init call to sync with database (5 required for my Roto cover)
            for init_call_count in range(1,6):
                _LOGGER.debug(
                    "Init call to %s:%s #%d", un, 1, init_call_count)
                await self.stop(':'.join((str(un), '1')))
                # 0.5 to 0.9 seconds (works with my Roto cover)
                time.sleep(randrange(5, 10, 1) / 10)
