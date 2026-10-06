import json
import unittest

from pipeline.preprocessing.experiments.spark.runtime.repository_profile_summary import summarize, write_summary


def event_log(tmp_path, events, *, suffix=""):
    path = tmp_path / f"events{suffix}"
    path.write_text("\n".join(json.dumps(item) for item in events) + "\n", encoding="utf-8")
    return path


def task(stage, task_id, runtime, *, attempt=0, success=True, cpu=100, spill=0):
    return {
        "Event": "SparkListenerTaskEnd", "Stage ID": stage,
        "Stage Attempt ID": attempt, "Task Info": {"Task ID": task_id},
        "Task End Reason": {"Reason": "Success" if success else "FetchFailed"},
        "Task Metrics": {"Executor Run Time": runtime, "Executor CPU Time": cpu,
                          "JVM GC Time": 3, "Memory Bytes Spilled": spill,
                          "Disk Bytes Spilled": 7, "Input Metrics": {"Bytes Read": 11},
                          "Output Metrics": {"Bytes Written": 13},
                          "Shuffle Read Metrics": {"Local Bytes Read": 17, "Remote Bytes Read": 19},
                          "Shuffle Write Metrics": {"Shuffle Bytes Written": 23}},
    }


class RepositoryProfileSummaryTest(unittest.TestCase):
  def test_groups_jobs_and_deduplicates_retries_and_shared_stage(self):
    tmp_path = self._tmp()
    events = [
        {"Event": "SparkListenerApplicationStart"},
        {"Event": "SparkListenerJobStart", "Stage IDs": [1, 2],
         "Properties": {"spark.jobGroup.id": "repository-profile:01:join"}},
        {"Event": "SparkListenerJobStart", "Stage IDs": [2],
         "Properties": {"spark.jobGroup.id": "repository-profile:02:write"}},
        task(1, 0, 10), task(1, 0, 10, success=False),  # duplicate attempt event ignored
        task(1, 0, 4, attempt=1, success=False),
        task(2, 0, 20), task(2, 1, 30, success=False),
        {"Event": "SparkListenerApplicationEnd"},
    ]
    result = summarize(event_log(tmp_path, events))

    assert result["incomplete_log"] is False
    assert result["task_attempt_count"] == 4
    assert [row["action"] for row in result["profiles"]] == ["join"]
    row = result["profiles"][0]
    assert row["stage_ids"] == [1, 2]
    assert row["shared_stage_count"] == 1
    assert (row["task_attempt_count"], row["successful_task_count"], row["failed_task_count"]) == (4, 2, 2)
    assert row["metrics"]["executor_run_time_ms"] == 64
    assert row["metric_coverage"]["executor_run_time_ms"] == 4


  def test_missing_metric_is_not_fabricated(self):
    tmp_path = self._tmp()
    events = [
        {"Event": "SparkListenerJobStart", "Stage IDs": [3],
         "Properties": {"spark.jobGroup.id": "repository-profile:1:validate"}},
        task(3, 0, 8),
    ]
    events[-1]["Task Metrics"].pop("Output Metrics")
    row = summarize(event_log(tmp_path, events))["profiles"][0]
    assert row["metrics"]["output_bytes"] == 0
    assert row["metric_coverage"]["output_bytes"] == 0


  def test_truncated_or_malformed_line_marks_summary_incomplete(self):
    tmp_path = self._tmp()
    path = tmp_path / "events"
    path.write_text(json.dumps({"Event": "SparkListenerApplicationStart"}) + "\n{" + "\n", encoding="utf-8")
    result = summarize(path)
    assert result["incomplete_log"] is True
    assert result["malformed_line_count"] == 1


  def test_output_is_exclusive(self):
    tmp_path = self._tmp()
    events = event_log(tmp_path, [])
    output = tmp_path / "summary.json"
    write_summary(events, output)
    with self.assertRaises(FileExistsError):
        write_summary(events, output)
    assert json.loads(output.read_text(encoding="utf-8"))["format"] == "spark_repository_profile_summary_v1"

  def test_skips_crc_and_rejects_multiple_apps_or_compressed_logs(self):
    tmp_path = self._tmp()
    path = event_log(tmp_path, [{"Event": "SparkListenerApplicationStart"}])
    (tmp_path / "events.crc").write_bytes(b"checksum")
    result = summarize(tmp_path)
    assert result["applications"] == 1
    (tmp_path / "other.gz").write_bytes(b"compressed")
    with self.assertRaises(ValueError):
      summarize(tmp_path)

  def test_rejects_multiple_applications(self):
    tmp_path = self._tmp()
    event_log(tmp_path, [{"Event": "SparkListenerApplicationStart"}], suffix="-a")
    event_log(tmp_path, [{"Event": "SparkListenerApplicationStart"}], suffix="-b")
    with self.assertRaises(ValueError):
      summarize(tmp_path)

  @staticmethod
  def _tmp():
    import tempfile
    from pathlib import Path
    return Path(tempfile.mkdtemp())


if __name__ == "__main__":
    unittest.main()
