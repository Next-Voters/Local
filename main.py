"""Entrypoint shim that delegates to the NV Local multi-city runner."""

from runners.run_container_job import main as runner_main


if __name__ == "__main__":
    raise SystemExit(runner_main())
