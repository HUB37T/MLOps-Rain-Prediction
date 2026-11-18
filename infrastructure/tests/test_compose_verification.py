"""Test operator controls, not a substitute for real VM persistence evidence."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("verify_compose", ROOT / "scripts/verify_compose.py")
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)


class VerificationControlsTests(unittest.TestCase):
    def test_default_mode_never_recreates_or_writes_container_data(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(verify, "REPO", Path(tmp)), \
             patch("sys.argv", ["verify_compose.py"]), \
             patch.object(verify, "compose") as compose, \
             patch.object(verify, "communicate", return_value={"metadata": "OK"}), \
             patch.object(verify, "marker") as marker, \
             patch.object(verify, "experiment_request") as experiment, \
             patch("builtins.print"):
            verify.main()
            self.assertEqual([c.args for c in compose.call_args_list],
                             [("config", "--quiet"), ("ps",)])
            marker.assert_not_called()
            experiment.assert_not_called()

    def test_explicit_persistence_recreates_without_down_or_volume_delete(self):
        markers = {}

        def marker(service, path, value=None):
            if value is not None:
                markers[path] = value
            return markers[path]

        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(verify, "REPO", Path(tmp)), \
             patch("sys.argv", ["verify_compose.py", "--persistence"]), \
             patch.object(verify, "compose") as compose, \
             patch.object(verify, "communicate", return_value={"metadata": "OK"}), \
             patch.object(verify, "marker", side_effect=marker), \
             patch.object(verify, "experiment_request", side_effect=[
                 {"experiment_id": "123"}, {"experiments": [{"experiment_id": "123"}]}]), \
             patch("builtins.print"):
            verify.main()
            calls = [c.args for c in compose.call_args_list]
            self.assertIn(("up", "-d", "--no-build", "--force-recreate", "--wait",
                           "--wait-timeout", "360"), calls)
            self.assertFalse(any("down" in call or "-v" in call for call in calls))
            report = json.loads(next(Path(tmp).rglob("report-*.json")).read_text())
            self.assertEqual(report["persistence"]["status"], "passed")
            self.assertEqual(len(markers), 3)

    def test_missing_metadata_after_recreation_is_a_failure(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(verify, "REPO", Path(tmp)), \
             patch("sys.argv", ["verify_compose.py", "--persistence"]), \
             patch.object(verify, "compose"), \
             patch.object(verify, "communicate", return_value={}), \
             patch.object(verify, "uuid") as uuid, \
             patch.object(verify, "marker", return_value="key"), \
             patch.object(verify, "experiment_request", side_effect=[
                 {"experiment_id": "123"}, {"experiments": []}]), \
             patch("builtins.print"):
            uuid.uuid4.return_value.hex = "key"
            with self.assertRaisesRegex(RuntimeError, "did not survive"):
                verify.main()
            self.assertEqual(list(Path(tmp).rglob("report-*.json")), [])
