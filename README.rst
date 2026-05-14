TaraMeteo
=========

.. image:: https://github.com/taradix/tarameteo/workflows/test/badge.svg
    :target: https://github.com/taradix/tarameteo/actions
.. image:: https://github.com/taradix/tarameteo/workflows/deploy/badge.svg
    :target: https://meteo.taram.ca

Weather in Notre-Dame-du-Laus.

Provision a new sensor
----------------------

Generate a key and client certificate for a new sensor::

    export PKI_API_TOKEN=<CA_TOKEN>
    tarameteo-pki issue <device_id>

Outputs:

- ``<device_id>.key`` — private key (mode 0600)
- ``<device_id>.pem`` — client certificate (CN = ``<device_id>``)
- ``ca.pem`` — CA certificate

Flash a sensor
--------------

Certificates are embedded into the firmware at build time. Set ``SENSOR_ID``
to the device identifier (used as the certificate CN and MQTT topic)::

    SENSOR_ID=outdoor-north uv run pio run -e esp32 --target upload

On first boot, the sensor enters **provisioning mode** (WiFi AP
``TaraMeteoProv-XXXX``) where you provide WiFi credentials and GPS location
via a web form at ``http://192.168.4.1``.

To erase and re-provision::

    uv run pio run -t erase
    SENSOR_ID=outdoor-north uv run pio run -e esp32 --target upload

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
