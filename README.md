# sdx-end-to-end-tests
SDX End to End tests

The AtlanticWave-SDX end-to-end tests are being developed at AMPATH to leverage AMPATH's Gitlab runners and environment. Once tests are created, we will move the environment to Github actions. Please contact the FIU SDX team in case you need access to the end-to-end tests. For now, the pipeline definition is defined at gitlab-ci.yml on FIU's Gitlab instance. All tests and setup scripts are based on this repo. Thus:
- If you need to change the pipeline execution steps/script, that have to be done at FIU's GitLab
- If you want to change tests, environment variables, setup scripts, etc, you have to use this repo

Just for the sake of clarification, here is the current `gitlab-ci.yml` (just for better understand of how the pipeline is actually executed -- this can be outdated very easily! we will try our best to keep it updated):
```
variables:
  MONGO_HOST_SEEDS: "mongo:27017"
  MONGO_INITDB_ROOT_USERNAME: root_user
  MONGO_INITDB_ROOT_PASSWORD: root_pw
  RABBITMQ_DEFAULT_USER: testsdx1
  RABBITMQ_DEFAULT_PASS: testsdx1

stages:
  - tests

end-to-end-testing:
  stage: tests
  tags:
    - privileged
  services:
    - name: mongo:7.0
      alias: mongo
    - name: rabbitmq:latest
      alias: mq1
    - name: ampath/kytos-sdx:latest
      entrypoint:
        - "/bin/bash"
        - "-x"
        - "-c"
        - |
          # wait for project clone/checkout
          until [ -f "$CI_PROJECT_DIR/.git/index" -a ! -f "$CI_PROJECT_DIR/.git/index.lock" ]; do sleep 1; done
          # wait for main script to start and export other service hosts
          while [ ! -f $CI_PROJECT_DIR/hosts ]; do sleep 1; done
          cat $CI_PROJECT_DIR/hosts >> /etc/hosts
          # actual steps to setup the service
          source $CI_PROJECT_DIR/sdx-end-to-end-tests/env/ampath.env
          python3 $CI_PROJECT_DIR/sdx-end-to-end-tests/setup-mongo-auth.py
          rsyslogd
          kytosd --database mongodb
          tail -f /dev/null
      alias: ampath
    - name: ampath/kytos-sdx:latest
      entrypoint:
        - "/bin/bash"
        - "-x"
        - "-c"
        - |
          # wait for project clone/checkout
          until [ -f "$CI_PROJECT_DIR/.git/index" -a ! -f "$CI_PROJECT_DIR/.git/index.lock" ]; do sleep 1; done
          # wait for main script to start and export other service hosts
          while [ ! -f $CI_PROJECT_DIR/hosts ]; do sleep 1; done
          cat $CI_PROJECT_DIR/hosts >> /etc/hosts
          # actual steps to setup the service
          source $CI_PROJECT_DIR/sdx-end-to-end-tests/env/sax.env
          python3 $CI_PROJECT_DIR/sdx-end-to-end-tests/setup-mongo-auth.py
          rsyslogd
          kytosd --database mongodb
          tail -f /dev/null
      alias: sax
    - name: ampath/kytos-sdx:latest
      entrypoint:
        - "/bin/bash"
        - "-x"
        - "-c"
        - |
          # wait for project clone/checkout
          until [ -f "$CI_PROJECT_DIR/.git/index" -a ! -f "$CI_PROJECT_DIR/.git/index.lock" ]; do sleep 1; done
          # wait for main script to start and export other service hosts
          while [ ! -f $CI_PROJECT_DIR/hosts ]; do sleep 1; done
          cat $CI_PROJECT_DIR/hosts >> /etc/hosts
          # actual steps to setup the service
          source $CI_PROJECT_DIR/sdx-end-to-end-tests/env/tenet.env
          python3 $CI_PROJECT_DIR/sdx-end-to-end-tests/setup-mongo-auth.py
          rsyslogd
          kytosd --database mongodb
          tail -f /dev/null
      alias: tenet
    - name: awsdx/sdx-lc:latest
      entrypoint:
        - "/bin/bash"
        - "-x"
        - "-c"
        - |
          # wait for project clone/checkout
          until [ -f "$CI_PROJECT_DIR/.git/index" -a ! -f "$CI_PROJECT_DIR/.git/index.lock" ]; do sleep 1; done
          # wait for main script to start and export other service hosts
          while [ ! -f $CI_PROJECT_DIR/hosts ]; do sleep 1; done
          cat $CI_PROJECT_DIR/hosts >> /etc/hosts
          # actual steps to setup the service
          source $CI_PROJECT_DIR/sdx-end-to-end-tests/env/ampath-lc.env
          python3 $CI_PROJECT_DIR/sdx-end-to-end-tests/setup-mongo-auth.py
          python3 $CI_PROJECT_DIR/sdx-end-to-end-tests/wait-rabbit.py
          python3 -m uvicorn sdx_lc.app:asgi_app --host 0.0.0.0 --port 8080
      command: [""]
      alias: ampath-lc
    - name: awsdx/sdx-lc:latest
      entrypoint:
        - "/bin/bash"
        - "-x"
        - "-c"
        - |
          # wait for project clone/checkout
          until [ -f "$CI_PROJECT_DIR/.git/index" -a ! -f "$CI_PROJECT_DIR/.git/index.lock" ]; do sleep 1; done
          # wait for main script to start and export other service hosts
          while [ ! -f $CI_PROJECT_DIR/hosts ]; do sleep 1; done
          cat $CI_PROJECT_DIR/hosts >> /etc/hosts
          # actual steps to setup the service
          source $CI_PROJECT_DIR/sdx-end-to-end-tests/env/sax-lc.env
          python3 $CI_PROJECT_DIR/sdx-end-to-end-tests/setup-mongo-auth.py
          python3 $CI_PROJECT_DIR/sdx-end-to-end-tests/wait-rabbit.py
          python3 -m uvicorn sdx_lc.app:asgi_app --host 0.0.0.0 --port 8080
      command: [""]
      alias: sax-lc
    - name: awsdx/sdx-lc:latest
      entrypoint:
        - "/bin/bash"
        - "-x"
        - "-c"
        - |
          # wait for project clone/checkout
          until [ -f "$CI_PROJECT_DIR/.git/index" -a ! -f "$CI_PROJECT_DIR/.git/index.lock" ]; do sleep 1; done
          # wait for main script to start and export other service hosts
          while [ ! -f $CI_PROJECT_DIR/hosts ]; do sleep 1; done
          cat $CI_PROJECT_DIR/hosts >> /etc/hosts
          # actual steps to setup the service
          source $CI_PROJECT_DIR/sdx-end-to-end-tests/env/tenet-lc.env
          python3 $CI_PROJECT_DIR/sdx-end-to-end-tests/setup-mongo-auth.py
          python3 $CI_PROJECT_DIR/sdx-end-to-end-tests/wait-rabbit.py
          python3 -m uvicorn sdx_lc.app:asgi_app --host 0.0.0.0 --port 8080
      command: [""]
      alias: tenet-lc
    - name: awsdx/sdx-controller:latest
      entrypoint:
        - "/bin/bash"
        - "-x"
        - "-c"
        - |
          # wait for project clone/checkout
          until [ -f "$CI_PROJECT_DIR/.git/index" -a ! -f "$CI_PROJECT_DIR/.git/index.lock" ]; do sleep 1; done
          # wait for main script to start and export other service hosts
          while [ ! -f $CI_PROJECT_DIR/hosts ]; do sleep 1; done
          cat $CI_PROJECT_DIR/hosts >> /etc/hosts
          # actual steps to setup the service
          source $CI_PROJECT_DIR/sdx-end-to-end-tests/env/sdx-controller.env
          python3 $CI_PROJECT_DIR/sdx-end-to-end-tests/setup-mongo-auth.py
          python3 $CI_PROJECT_DIR/sdx-end-to-end-tests/wait-rabbit.py
          python3 -m uvicorn sdx_controller.app:asgi_app --host 0.0.0.0 --port 8080
      command: [""]
      alias: sdx-controller
  image: italovalcy/mininet:latest
  script:
    # wait for project clone/checkout (relying on git index to indicate the clone/checkout is done)
    - until [ -f "$CI_PROJECT_DIR/.git/index" -a ! -f "$CI_PROJECT_DIR/.git/index.lock" ]; do sleep 1; done
    - git clone https://github.com/atlanticwave-sdx/sdx-end-to-end-tests $CI_PROJECT_DIR/sdx-end-to-end-tests
    - cp /etc/hosts $CI_PROJECT_DIR/
    - apt-get update && apt-get install -y tmux jq python3-pytest python3-requests
    - cd $CI_PROJECT_DIR/sdx-end-to-end-tests
    - python3 -m pytest tests/
```
