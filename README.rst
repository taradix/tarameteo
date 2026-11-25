TaraMeteo
=========

.. image:: https://github.com/taradix/tarameteo/workflows/test/badge.svg
    :target: https://github.com/taradix/tarameteo/actions
.. image:: https://github.com/taradix/tarameteo/workflows/deploy/badge.svg
    :target: https://meteo.taram.ca

Weather in Notre-Dame-du-Laus.

Provision a new sensor
----------------------

Every sensor runs the same firmware; its identity lives in the nvs
partition. On a new board, flash the firmware, then give it an identity::

    export PKI_API_TOKEN=<CA_TOKEN>
    make -C firmware factory PORT=<serial_port>

This derives the sensor ID from the board's MAC (like ``tm-3f9a1c``), issues
a never-expiring client certificate for it and writes the certificate, key,
CA and a BLE passkey into NVS. Write the printed ID and passkey on the sticker.

On first boot, the sensor enters **provisioning mode**: it advertises its ID
over Bluetooth for 5 minutes. Pair with the passkey from the sticker, then
enter WiFi credentials, a name and the sensor location in the TaraMeteo app.
The sensor saves them once it has joined the WiFi; if it can't, it reports
the error and waits for another try.

To move a sensor to a new network, power-cycle it: every power-on opens
provisioning mode for 2 minutes, then the sensor carries on with its saved
settings. Without the app, ``firmware/scripts/provision.py`` does the same
from a computer.

To shelve a sensor or give it away, power-cycle it and pick **Reset a
station** in the app (or run ``provision.py <id> --reset``). It forgets its
WiFi, name, location and server, keeps its identity, and stays asleep until
it is powered on again, when it waits to be set up like a new one. The
backend keeps its past readings, and it drops off the map 90 days after its
last one.

Flash a sensor
--------------

To update the firmware, flash the app only; NVS keeps the identity and WiFi
settings::

    uv run pio run -e esp32 --target upload

Never erase the chip (``pio run -t erase``) or move the nvs partition in
``firmware/partitions.csv``: both lose the identity, and the board then needs
a new one from ``make factory``.

To monitor serial output::

    uv run pio device monitor

Wire a sensor
-------------

This configuration uses the
`Seeed Studio XIAO ESP32-C3 <https://wiki.seeedstudio.com/XIAO_ESP32C3_Getting_Started/>`_
and the
`Adafruit BME280 Sensor <https://www.adafruit.com/product/2652>`_
in I²C mode.

+----------------------+---------------------------+------------------------------+
| BME280 Pin           | XIAO ESP32-C3 Pin         | Description                  |
+======================+===========================+==============================+
|                      | 5V                        | 3xAA Battery pack (+)        |
+----------------------+---------------------------+------------------------------+
| GND                  | GND                       | 3xAA Battery pack (-)        |
+----------------------+---------------------------+------------------------------+
| VIN                  | 3V3                       | Power supply (3.3V)          |
+----------------------+---------------------------+------------------------------+
| SCK                  | SCL (I²C Clock)           | Clock line                   |
+----------------------+---------------------------+------------------------------+
| SDI                  | SDA (I²C Data)            | Data line                    |
+----------------------+---------------------------+------------------------------+
