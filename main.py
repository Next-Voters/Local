"""CLI entrypoint for single-city NV Local pipeline runs."""

import logging

from dotenv import load_dotenv

from pipelines.nv_local import main as pipeline_main

load_dotenv()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    pipeline_main()
