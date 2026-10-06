import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).parents[2] / "scripts" / "service-data-migration" / "local_dump_client.py"
SPEC = importlib.util.spec_from_file_location("local_dump_client", MODULE_PATH)
client = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(client)


def inspect_payload(*, source: str = "pickage-267-validation", image: str = "postgres:16-alpine", password: str | None = None):
    env = ["POSTGRES_HOST_AUTH_METHOD=trust", "POSTGRES_DB=pickage_267_full_defaulted"]
    if password is not None:
        env.append(f"POSTGRES_PASSWORD={password}")
    return [{
        "State": {"Running": True},
        "HostConfig": {"NetworkMode": "none"},
        "Mounts": [{"Destination": "/var/lib/postgresql/data"}],
        "Config": {"Image": image, "Env": env, "Labels": {}},
    }]


class LocalDumpClientTests(unittest.TestCase):
    @patch.object(client, 'source_id', return_value='source-id')
    def test_reuse_rejects_missing_host_or_wrong_mount(self, source_id):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            info = {'Config': {'Labels': {'pickage.task':'341-local-dump-client', 'pickage.source':'source'},
                               'Env':['PGHOST=127.0.0.1']},
                    'HostConfig': {'NetworkMode':'container:source-id'},
                    'Mounts': [{'Type':'bind','Destination':'/work','Source':str(root)}]}
            client.validate_helper(info, source='source', archive=root)
            info['Config']['Env'] = []
            with self.assertRaises(client.DumpClientError):
                client.validate_helper(info, source='source', archive=root)
            info['Config']['Env'] = ['PGHOST=127.0.0.1']
            with self.assertRaises(client.DumpClientError):
                client.validate_helper(info, source='source', archive=root/'different')

    @patch.object(client, "run")
    def test_start_uses_shared_network_and_only_work_mount(self, run):
        run.side_effect = [
            type("Result", (), {"returncode": 0, "stdout": json.dumps(inspect_payload()), "stderr": ""})(),
            type("Result", (), {"returncode": 1, "stdout": "", "stderr": ""})(),
            type("Result", (), {"returncode": 0, "stdout": "helper", "stderr": ""})(),
        ]
        with tempfile.TemporaryDirectory() as raw:
            args = type("Args", (), {"source_container": "pickage-267-validation", "archive_dir": Path(raw), "database": "pickage_267_full_defaulted"})()
            result = client.start(args)
        command = run.call_args_list[2].args[0]
        self.assertIn("--network", command)
        self.assertIn("container:pickage-267-validation", command)
        self.assertEqual(command.count("--volume"), 1)
        self.assertIn("--env", command)
        self.assertIn("PGPASSWORD", command)
        self.assertFalse(result["reused"])

    @patch.object(client, "checked")
    @patch.object(client, "source_details", return_value=("postgres:16-alpine", "postgres", None))
    @patch.object(client, "inspect_existing")
    def test_stop_requires_task_label(self, inspect_existing, source_details, checked):
        inspect_existing.return_value = {"Config": {"Labels": {"pickage.task": "other", "pickage.source": "pickage-267-validation"}}}
        args = type("Args", (), {"source_container": "pickage-267-validation"})()
        with self.assertRaises(client.DumpClientError):
            client.stop(args)
        checked.assert_not_called()

    @patch.object(client, "source_details", return_value=("postgres:16-alpine", "postgres", None))
    @patch.object(client, "inspect_existing")
    def test_probe_does_not_return_password(self, inspect_existing, source_details):
        inspect_existing.return_value = {
            "Id": "helper-id",
            "State": {"Running": True},
            "HostConfig": {"NetworkMode": "container:source-id"},
            "Mounts": [{"Type": "volume", "Destination": "/var/lib/postgresql/data"},
                       {"Type": "bind", "Source": str(Path("data/service-data-migration/341/local-dump-probe").resolve()), "Destination": "/work"}],
            "Config": {"Labels": {"pickage.task": "341-local-dump-client", "pickage.source": "pickage-267-validation"},
                       "Env": ["PGHOST=127.0.0.1"]},
        }
        with patch.object(client, "run", side_effect=[
            type("Result", (), {"returncode": 0, "stdout": json.dumps([{ "Id": "source-id" }]), "stderr": ""})(),
            type("Result", (), {"returncode": 0, "stdout": "ready", "stderr": ""})(),
            type("Result", (), {"returncode": 0, "stdout": "zstd", "stderr": ""})(),
        ]):
            args = type("Args", (), {"source_container": "pickage-267-validation", "database": "pickage_267_full_defaulted",
                                      "archive_dir": Path("data/service-data-migration/341/local-dump-probe")})()
            result = client.probe(args)
        self.assertNotIn("password", result)
        self.assertTrue(result["zstd_supported"])


if __name__ == "__main__":
    unittest.main()
