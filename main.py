"""Entrypoint shim that delegates to the NV Local pipeline runner."""

from pipelines.nv_local import main as pipeline_main


if __name__ == "__main__":
    pipeline_main()
