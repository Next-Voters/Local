"""CLI entrypoint for single-city NV Local pipeline runs."""

import logging

from pipelines.nv_local import main as pipeline_main


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    pipeline_main()
