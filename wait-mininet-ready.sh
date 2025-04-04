#!/bin/bash

while ! docker compose logs mininet -n 1 | grep -q "tail -f /dev/null"; do
	sleep 2
done
docker compose exec -it mininet pip install requests
