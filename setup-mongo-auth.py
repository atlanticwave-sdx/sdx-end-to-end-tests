import time
import os
from pymongo import MongoClient
HOST = os.environ.get("MONGO_HOST_SEEDS", "mongo:27017")
USER = os.environ.get("MONGO_USERNAME")
PASS = os.environ.get("MONGO_PASSWORD")
DBNAME = os.environ.get("MONGO_DBNAME")
client = MongoClient(
    HOST.split(","),
    username=os.environ.get("MONGO_INITDB_ROOT_USERNAME", "root_user"),
    password=os.environ.get("MONGO_INITDB_ROOT_PASSWORD", "root_pw"),
)
for i in range(30):
    try:
        client[DBNAME].command('createUser', USER, pwd=PASS, roles=[{'role': 'readWrite', 'db': DBNAME}])
        print("mongodb created successfully for DB=%s user=%s" % (DBNAME, USER))
        break
    except Exception as exc:
        print("Error creating mongo DB: %s" % str(exc))
    time.sleep(2)
else:
    print("fail to create mongodb")

for i in range(30):
    print("Trying to connect to Mongo")
    try:
        CONN_STR=f"mongodb://{USER}:{PASS}@{HOST}/{DBNAME}"
        client = MongoClient(CONN_STR)
        print(client.list_database_names())
        print("Sucessfully connected to Mongo")
        break
    except Exception as exc:
        print("Error connecting to Mongo: %s" % str(exc))
    time.sleep(2)
