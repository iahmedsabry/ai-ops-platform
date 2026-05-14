"""Global test hooks: skip real in-cluster K8s config when importing sandbox."""

from unittest.mock import patch

patch("kubernetes.config.load_incluster_config", lambda: None).start()
