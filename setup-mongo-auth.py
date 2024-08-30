import time
import os
from pymongo import MongoClient
HOST = os.environ.get("MONGO_HOST_SEEDS", "mongo:27017")
USER = os.environ.get("MONGO_USERNAME")
PASS = os.environ.get("MONGO_PASSWORD")
DBNAME = os.environ.get("MONGO_DBNAME")
ROOT_USER = os.environ.get("MONGO_INITDB_ROOT_USERNAME", "root_user")
ROOT_PASS = os.environ.get("MONGO_INITDB_ROOT_PASSWORD", "root_pw")

if ROOT_USER != USER:
    client = MongoClient(
        HOST.split(","),
        username=ROOT_USER,
        password=ROOT_PASS
    )
    for i in range(60):
        try:
            client[DBNAME].command('createUser', USER, pwd=PASS, roles=[{'role': 'readWrite', 'db': DBNAME}])
            client[DBNAME].force_db_creation.insert_one({})
            print("mongodb created successfully for DB=%s user=%s" % (DBNAME, USER))
            break
        except Exception as exc:
            print("Error creating mongo DB: %s" % str(exc))
        time.sleep(2)
    else:
        print("fail to create mongodb")
        raise Exception("timeout creating mongodb/user")

for i in range(60):
    print("Trying to connect to Mongo")
    try:
        CONN_STR=f"mongodb://{USER}:{PASS}@{HOST}/?authSource={DBNAME}"
        client = MongoClient(CONN_STR)
        assert client.list_database_names() == [DBNAME]
        print("Sucessfully connected to Mongo")
        break
    except Exception as exc:
        print("Error connecting to Mongo: %s" % str(exc))
    time.sleep(2)
else:
    raise Exception("timeout waiting for mongodb/user")
