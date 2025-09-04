#!/bin/bash

echo -n "Waiting mininet to be ready..."
while ! docker compose logs mininet -n 1 | grep -q "tail -f /dev/null"; do
	sleep 2
	echo -n "."
done
echo "ok"
