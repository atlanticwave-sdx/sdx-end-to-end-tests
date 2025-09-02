# Using SDX end-to-end test during the development life cycle

This document describe some steps that can be used to support the development life cycle using end-to-end tests to validate the impact of changes, avoid regressions, etc.

## Test changes on SDX-Controller

The following steps can be used to test changes on SDX-Controller using the end-to-end tests. We start by first getting ready with standard end-to-end tests:

```
git clone http://github.com/atlanticwave-sdx/sdx-end-to-end-tests
cd sdx-end-to-end-tests
docker compose pull
```

Now we download SDX-Controller source code, switch to the branch of interest (the branch where your changes are):
```
git clone http://github.com/atlanticwave-sdx/sdx-controller
cd sdx-controller
git checkout my-branch-name
git pull
```

Next we will build the docker image. Notice that we will force the tag name to overwrite the standard image referred in docker compose:
```
docker build -t awsdx/sdx-controller:latest . 
```

Now we start the end-to-end tests environment with the following command (again notice the addition of the parameter `--pull never` to allow using the image we built above -- remember that we already pulled the latest changes on the other images in the first step):
```
docker compose up -d --pull never
```

Finally, you can run the end-to-end tests:
```
./wait-mininet-ready.sh
docker compose exec -it mininet python3 -m pytest tests/
```

After the end-to-end tests routine finishes its execution, all containers will remain active. Thus, you can still collect logs, analyze the outputs and troubleshoot. Once you are done, dont forget to clean up the environment:
```
docker compose down -v
```

## Test changes on SDX-LC, datamodel, PCE, Kytos OXPO, etc

Very similar to how we applied the changes to SDX-Controller, you can also do for SDX-LC and Kytos. Please refer to the docker-compose.yml for the specific image name.

For `datamodel` and `PCE`, since they dont have a docker image specific for them, we have two approaches: 1) rebuild SDX-Controller changing the `pyproject.toml` with the branches/versions of interest for PCE and Datamodel; or 2) mount a local copy of PCE/Datamodel repositories into the container's installed Python libs (easiest).

1. Example changing `pyproject.yml`
```
git clone http://github.com/atlanticwave-sdx/sdx-controller
cd sdx-controller
git apply <<EOF
diff --git a/pyproject.toml b/pyproject.toml
index d060cc8..c816188 100644
--- a/pyproject.toml
+++ b/pyproject.toml
@@ -29,7 +29,7 @@ dependencies = [
     "pika >= 1.2.0",
     "dataset",
     "pymongo > 3.0",
-    "sdx-pce @ git+https://github.com/atlanticwave-sdx/pce@3.1.0.dev10",
+    "sdx-pce @ git+https://github.com/atlanticwave-sdx/pce@my-branch-name",
 ]

 [project.optional-dependencies]
EOF
```

2. Example mounting datamodel and pce into installed python libs:
```
git clone http://github.com/atlanticwave-sdx/datamodel
cd datamodel
# change whatever you need to change
cd ..

git clone http://github.com/atlanticwave-sdx/pce
cd pce
# change whatever you need to change
cd ..

git apply <<EOF
diff --git a/docker-compose.yml b/docker-compose.yml
index 8b430f2..0e2405f 100644
--- a/docker-compose.yml
+++ b/docker-compose.yml
@@ -158,6 +158,8 @@ services:
       - .env
     volumes:
       - .:/sdx-end-to-end-tests
+      - ./datamodel/src/sdx_datamodel:/opt/venv/lib/python3.11/site-packages/sdx_datamodel
+      - ./pce/src/sdx_pce:/opt/venv/lib/python3.11/site-packages/sdx_pce
     depends_on:
       mongo:
         condition: service_healthy
EOF
```
After this, you can run the standar procedure:

```
docker compose up -d
./wait-mininet-ready.sh
docker compose exec -it mininet python3 -m pytest tests/
```

## Run end-to-end tests interactively


