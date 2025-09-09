#!/bin/bash

echo "-> starting mininet"
docker compose exec -it mininet bash -c "tmux new-sess -d -s mn python3 -i start-mn.py"

echo "-> waiting switches to connect"
./scripts/wait-switches-connected.sh
