#!/usr/bin/python3

import os
import time
import pika

MQ_HOST = os.environ.get("MQ_HOST")
MQ_PORT = os.environ.get("MQ_PORT")
MQ_USER = os.environ.get("MQ_USER")
MQ_PASS = os.environ.get("MQ_PASS")

while True:
    try:
        print("Trying to connection to RabbitMQ host=%s port=%s user=%s" % (MQ_HOST, MQ_PORT, MQ_USER))
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(
                host=MQ_HOST,
                port=MQ_PORT,
                credentials=pika.PlainCredentials(username=MQ_USER, password=MQ_PASS),
            )
        )
        assert connection.is_open
        print("Connection to RabbitMQ established successfully")
        break
    except Exception as exc:
        print("error connecting to RabbitMQ: %s" % str(exc))
    time.sleep(5)
