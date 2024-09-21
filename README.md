# sdx-end-to-end-tests
SDX End to End tests

The AtlanticWave-SDX end-to-end tests are being developed at AMPATH to leverage AMPATH's Gitlab runners and environment. Once tests are created, we will move the environment to Github actions. Please contact the FIU SDX team in case you need access to the end-to-end tests. For now, the pipeline definition is defined at gitlab-ci.yml on FIU's Gitlab instance. All tests and setup scripts are based on this repo. Thus:
- If you need to change the pipeline execution steps/script, that have to be done at FIU's GitLab
- If you want to change tests, environment variables, setup scripts, etc, you have to use this repo

If you need to run the tests locally, you can run the following commands:

```
docker compose up -d
./wait-mininet-ready.sh
docker compose exec -it mininet python3 -m pytest tests/
```

After executing your tests, please clean up the environment before the next execution:
```
docker compose down -v
```

(for the future, we should provide means to clean up the setup before each tests)
