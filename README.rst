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

    export PKI_API_URL=https://meteo.taram.ca/api/certs
    export PKI_API_TOKEN=<CA_TOKEN>
    export PKI_OUTPUT_DIR=/path/to/sensor-tls
    tarameteo-pki rotate <device_id>

Outputs written to ``$PKI_OUTPUT_DIR``:

- ``<device_id>.key`` — private key (mode 0600)
- ``<device_id>.pem`` — client certificate (CN = ``<device_id>``)
- ``ca.pem`` — CA certificate
