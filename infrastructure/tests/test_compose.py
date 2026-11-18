"""Validate the actual Compose-rendered manifest without starting containers."""
import json
import os
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]


class ComposeManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        env = dict(os.environ, API_PORT="8000", WEB_PORT="8080", MLFLOW_PORT="5000",
                   PREDICTION_DATA_DIR="./data/predictions",
                   MLFLOW_BACKEND_DIR="./data/mlflow/backend",
                   MLFLOW_ARTIFACT_DIR="./data/mlflow/artifacts")
        result = subprocess.run(
            ["docker", "compose", "-f", str(ROOT / "docker-compose.yaml"),
             "config", "--format", "json"],
            cwd=ROOT, env=env, check=True, text=True, capture_output=True,
        )
        cls.config = json.loads(result.stdout)

    def test_all_services_share_explicit_bridge(self):
        self.assertEqual(self.config["networks"]["rain-network"]["driver"], "bridge")
        for name in ("backend", "frontend", "mlflow"):
            self.assertIn("rain-network", self.config["services"][name]["networks"])

    def test_startup_waits_for_healthy_dependencies(self):
        services = self.config["services"]
        self.assertEqual(services["backend"]["depends_on"]["mlflow"]["condition"], "service_healthy")
        self.assertEqual(services["frontend"]["depends_on"]["backend"]["condition"], "service_healthy")
        self.assertIn("healthcheck", services["mlflow"])
        self.assertIn("healthcheck", services["backend"])

    def test_existing_persistent_data_paths_preserved(self):
        expected = {"backend": {"/app/data/predictions": "data/predictions"},
                    "mlflow": {"/mlflow/backend": "data/mlflow/backend",
                               "/mlflow/artifacts": "data/mlflow/artifacts"}}
        for service, targets in expected.items():
            mounts = {v["target"]: v for v in self.config["services"][service]["volumes"]}
            for target, relative in targets.items():
                self.assertEqual(mounts[target]["type"], "bind")
                self.assertEqual(Path(mounts[target]["source"]).resolve(), ROOT / relative)

    def test_tracking_uses_service_name_and_allows_internal_host(self):
        backend = self.config["services"]["backend"]
        self.assertEqual(backend["environment"]["MLFLOW_TRACKING_URI"], "http://mlflow:5000")
        command = self.config["services"]["mlflow"]["command"]
        self.assertIn("mlflow:*", command[command.index("--allowed-hosts") + 1].split(","))

    def test_tracking_ui_remains_localhost_only(self):
        self.assertEqual(self.config["services"]["mlflow"]["ports"][0]["host_ip"], "127.0.0.1")

    def test_single_canonical_manifest(self):
        self.assertTrue((ROOT / "docker-compose.yaml").is_file())
        self.assertFalse((ROOT / "docker-compose.yml").exists())


if __name__ == "__main__":
    unittest.main()
