# Becker cover support for Home Assistant

A native Home Assistant component to control Becker RF shutters with a Becker Centronic USB stick.
It works with the Becker ***Centronic USB Stick*** with the Becker order number ***4035 200 041 0*** and ***4035 000 041 0***.
It works for the Becker ***Centronic*** roller shutters, blinds and sun protection as well as for Roto roof windows with RF remotes.  
It is based on the work of [ole](https://github.com/ole1986) and [Nicolas Berthel](https://github.com/nicolasberthel).

The Becker integration currently supports the following cover operations:
- Open
- Close
- Stop
- Open tilt
- Close tilt
- Set cover position

There are three ways to track position of the cover:
- Add the travel time to configuration
- Provide a value template e.g. to use sensors to set the current position
- Track the cover commands from Becker remotes

# Installation

1. Add [this](https://github.com/RainerStaude/hass-becker-component-plus-pybecker) repository to HACS custom
   repositories (preferred).  
   Alternatively copy the files of this [this](https://github.com/RainerStaude/hass-becker-component-plus-pybecker)
   repository into the custom_components folder of your HA configuration directory.  
2. Plug the Becker USB stick into any free USB port. It is a good practice to add a short USB extension cable
   and place the Becker USB stick away from other RF sources.  
3. Add the Becker integration to your configuration.  
4. Reboot Home Assistant

# Configuration
## Basic configuration
```yaml
cover:
  - platform: becker
    covers:
      # Use unique names for each cover like kitchen, bedroom or living_room
      kitchen:
        friendly_name: "Kitchen Cover"
        # Becker Centronic USB stick provides up to five units (1-5) with up to seven (1-7) channels
        # Unit 1 - Channel 2
        channel: "1"
      bedroom:
        friendly_name: "Bedroom Cover"
        # Unit 1 - Channel 2
        channel: "2"
      living_room:
        friendly_name: "Living room Cover"
        # Use Unit 2 - Channel 1
        channel: "2:1"
```
Note: The channel needs to be a string!

## Platform configuration
If you use the Becker integration with the ***Home Assistant Operating System***, 
the default device path for the USB Stick should work. The default path is:  
`/dev/serial/by-id/usb-BECKER-ANTRIEBE_GmbH_CDC_RS232_v125_Centronic-if00`  
If you run Home Assistant within a Virtual Machine or a Docker container, it 
might be useful use a different device path.  
Note: The serial port is opened using 
the [pySerial serial_for_url handler](https://pyserial.readthedocs.io/en/latest/url_handlers.html).
Therefore connections e.g.  over a TCP/IP socket are supported as well.

The Becker integration uses a database file `centronic-stick.db` located in the 
Home Assistant configuration folder to store an incremental number for each unit.
You can change the filename if needed. If the database file gets lost it will be
restored on startup automatically. In case any cover does not respond press the STOP 
button several times.
```yaml
cover:
  - platform: becker
    device: "/dev/my-becker-centronic-usb"
    filename: "my-centronic-stick.db"
```

## Position by Travel Time
There is no feedback from the covers available! In order to track the position of
the cover, it is recommended to add the travel time for each cover. Determine the
movement time in ***seconds*** for each cover from closed to open position. To
improve the precision, add the movement time from open to closed position as well.  
This will also enable the ability to set the cover position from Home Assistant user 
interface or through the service `cover.set_cover_position`.
```yaml
cover:
  - platform: becker
    covers:
      living_room:
        friendly_name: "Living room Cover"
        channel: "2:1"
        # The travel time for direction up is sufficient if travel time for up and down are equal
        travelling_time_up: 30
        # Optional travel time for direction down
        travelling_time_down: 26.5
```

## Position by value template
In some cases it might be useful to add a value template to determine the position
of your cover. For example for a roof window with rain sensor. In case of rain, 
the roof window will close, but you cannot determine this without an additional 
sensor.  
Every time the template generates a new result, the position of the cover is overwritten 
by the result of the template.  
The following results are valid:
- any number between `0` and `100` where `0` is `closed` and `100` is `open`
- logic values where
  - `'closed'`, `'false'`, `False` are `closed`
  - `'open'`, `'true'`, `True` are `open`
- unknown values `'unknown'`, `'unavailable'`, `'none'`, `None`  
The unknown values are useful to set the position only to confirm one specific 
position, like closed in the example below. For any other values the position 
will not changed. This allows to use the value template in conjunction with the position 
by travel time.
```yaml
cover:
  - platform: becker
    covers:
      roof_window:
        friendly_name: "Roof window"
        channel: "3:1"
        travelling_time_up: 15
        # Set position to closed (0) if sensor.roof_window is closed, otherwise keep value
        value_template: "{{ 0 if is_state('sensor.roof_window', 'closed') else None }}"
```

## Position tracking for cover commands from Becker remotes
Usually there is at least one remote, the master remote, used to control the cover.
The remote communicates directly with the cover. It is possible to receive and track 
all remote commands within home assistant. Therefore the position of the cover
is updated whenever a remote command is received.  
In order to determine the remote ID, it es necessary to enable debug log messages
(see troubleshooting). The debug message will look as follows:  
`... DEBUG ... \[custom_components.becker.pybecker.becker_helper]` Received packet: 
unit_id: `12345`, channel: `2`, command: HALT, argument: 0, packet: ...
```yaml
cover:
  - platform: becker
    covers:
      living_room:
        friendly_name: "Living room Cover"
        channel: "2:1"
        travelling_time_up: 30
        travelling_time_down: 26.5
        # The remote ID consists of the unit_id and the channel separated by a colon
        # Multiple ID's separated by comma are possible
        remote_id: "12345:2"
```

## Intermediate cover position
Becker covers supports two intermediate positions. One when opening the cover 
and one when closing the cover. Please see the manual of your cover to see how
to program these intermediate positions in your cover.  
Your cover will travel to the corresponding intermediate position if your double
tab the UP or DOWN button on your remote.  
The default intermediate positions in the Becker integration are `25` for UP 
direction and `75` for DOWN direction, where `0` is `closed` and `100` is `open`.
This behavior is imitated by the Becker integration in Home Assistant. To imitate
the cover movement properly in Home Assistant it is required to set the positions properly.  
You can calculate the `intermediate_position_up`. You need to measure the runtime from 
closed position to the intermediate position in direction UP (double tap UP 
on your remote). Divide the measured time by the `travelling_time_up` and 
multiply the result by `100`.  
You can do the same for the `intermediate_position_up`. Measure the runtime from 
closed position to the intermediate position in direction DOWN (double tap DOWN on 
your remote). Divide the measured time by the `travelling_time_up` and multiply 
the result by `100`.
```yaml
  - platform: becker
    covers:
      kitchen:
        friendly_name: "Kitchen Cover"
        channel: "1"
        intermediate_position_up: 70
        intermediate_position_down: 40
```
If you have not programmed any intermediate positions in your cover, you should 
disable the intermediate cover position.
```yaml
  - platform: becker
    covers:
      kitchen:
        friendly_name: "Kitchen Cover"
        channel: "1"
        intermediate_position: off
```

## Tilt intermediate
The Becker integration provide the ability to control the intermediate position from 
Home Assistant user interface. Therefore the tilt functionality of Home Assistant is used 
to issue the commands to drive to intermediate positions.
If you don't want to control the intermediate positions from Home Assistant, you can 
disable the tilt functionality for each cover.  
This will also disable the service `cover.close_cover_tilt` and `cover.open_cover_tilt`.
```yaml
  - platform: becker
    covers:
      kitchen:
        friendly_name: "Kitchen Cover"
        channel: "1"
        tilt_intermediate: off
```
Note: You still need to set the intermediate cover position appropriately!

## Tilt blind
The Becker integration provides support for blinds. The Becker blinds allow to control
their tilt position by short press of the UP or DOWN button on their master remote. 
A long press of the UP or DOWN button fully open or closes the blinds.  
To control the tilt position of your blind and for proper tracking of your blind position, 
you need to enable `tilt_blind`. This changes the tilt functionality of Home Assistant 
from intermediate position to tilt blind. The default tilt time is 0.3 seconds. 
This time can be adapted to your needs.
```yaml
  - platform: becker
    covers:
      Living_room_blind:
        friendly_name: "Living room blind"
        channel: "2:2"
        tilt_blind: on
        tilt_time_blind: 0.5
```

# Pairing the Becker USB Stick with your covers
To use your cover in HA you need to pair it first with the Becker USB stick. The
pairing is always between your remote and the shutter. The shutter will react on 
the commands of all paired remotes.  
Usually you already have programmed your original remote as the master remote. It 
is not recommended to program the USB stick as the master remote! The USB stick is 
like an additional remote. Therefore the pairing procedure for the USB stick is 
the same as with additional remotes. Please refer to you manual for more details.  

You have to put your shutter in pairing mode before. This is done by pressing the 
program button of your master remote until you hear a "clac" noise

To pair your shutter run the service becker.pair once (see HA Developer Tools -> Services).
The shutter will confirm the successful pair with a single "clac" noise followed by a double "clac" noise.

Example data for service becker.pair:

```yaml
service: becker.pair
data:
  # Example data to pair your cover with USB stick unit 1 - channel 1
  channel: 1
  unit: 1
```

# Events for Remote Commands
In addition to processing remote commands to update cover states, the
integration also fires explicit events of type
`becker_remote_packet_received` for each command it receives from a remote.
Those events can be used to trigger automations when remote buttons are pressed
or for other custom purposes.

Each event contains data about the remote unit, channel and the command
that has been received, for instance:

```yaml
event_type: becker_remote_packet_received
data:
  unit: "12345"
  channel: "1"
  command: "up"
```

# Troubleshooting
If you have any trouble follow these steps:
- Restart Home Assistant after you have plugged in the USB stick
- Enable debug log for becker.  
Add the following lines to your configuration.yaml to enable debug log:

```yaml
logger:
  default: info
  logs:
    # This must correspond to the folder name of your /config/custom_components/becker folder
    custom_components.becker: debug
```

You can also change the log configuration dynamically by calling the `logger.set_level` service. 
This method allows you to enable debug logging only for a limited time:

```yaml
service: logger.set_level
data:
  custom_components.becker: debug
```

All messages are logged to the home-assistant.log file in your config folder.  
It is also helpful to find out the Remote ID of your Becker Remote. The message 
will be something like below every time you press a key on your Remote:  
`... DEBUG ... \[custom_components.becker.pybecker.becker_helper]` Received packet: 
unit_id: `12345`, channel: `2`, command: HALT, argument: 0, packet: ...

In case of any errors related to the Becker integration try to fix them.  
If you require additional help have a look at the 
[Home Assistant Community](https://community.home-assistant.io). There is already one thread about the 
Becker integration: 
[Integrating Becker Motors](https://community.home-assistant.io/t/integrating-becker-motors-in-to-hassio/151705)
Another way is to open a new issue on 
[GitHub](https://github.com/RainerStaude/hass-becker-component-plus-pybecker/issues).

To disable debug log for becker set the level back from `debug` to `info`.