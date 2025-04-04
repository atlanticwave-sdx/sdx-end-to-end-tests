#!/bin/bash
docker compose exec -it mininet python3 -m pytest tests/ --junitxml=/tmp/results.xml
