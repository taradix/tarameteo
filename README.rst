TaraMeteo
=========

.. image:: https://github.com/taradix/tarameteo/workflows/test/badge.svg
    :target: https://github.com/taradix/tarameteo/actions
.. image:: https://github.com/taradix/tarameteo/workflows/deploy/badge.svg
    :target: https://meteo.taram.ca

Weather in Notre-Dame-du-Laus.

Setup
-----

docker compose run -it --rm -p 80 certbot certbot certonly -v --standalone --non-interactive --agree-tos --deploy-hook /deploy-hook.sh -d meteo.taram.ca
