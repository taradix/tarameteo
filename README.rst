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

This picks a random sensor ID (like ``tm-3f9a1c``), issues a never-expiring
client certificate for it and writes the certificate, key, CA and a BLE
passkey into NVS. Write the printed ID and passkey on the sticker.

On first boot, the sensor enters **provisioning mode**: it advertises its ID
over Bluetooth. Pair with the passkey from the sticker, then enter WiFi
credentials and the sensor location in the TaraMeteo app.

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
