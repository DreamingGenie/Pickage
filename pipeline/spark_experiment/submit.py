"""spark-submit entry point (package imports work with --py-files)."""
from pipeline.spark_experiment.job import main

if __name__ == "__main__":
    raise SystemExit(main())
