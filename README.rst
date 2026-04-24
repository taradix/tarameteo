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
    tarameteo-pki rotate <device_id>

Outputs:

- ``<device_id>.key`` — private key (mode 0600)
- ``<device_id>.pem`` — client certificate (CN = ``<device_id>``)
- ``ca.pem`` — CA certificate
