from __future__ import annotations

from unittest import mock
from unittest.mock import patch

from src.utils.gpu import set_gpu_power_limit_if_needed


def test_default_behavior_present_gpu() -> None:
    # Mock os.popen to simulate GPU presence
    with patch("os.popen") as mock_popen:
        mock_popen.return_value.read.return_value = "NVIDIA GeForce RTX 3090"
        with patch("os.system") as mock_system:
            set_gpu_power_limit_if_needed()
            calls = [
                mock.call("/usr/bin/sudo /usr/bin/nvidia-smi -pm 1"),
                mock.call("/usr/bin/sudo /usr/bin/nvidia-smi -pl 250"),
            ]
            mock_system.assert_has_calls(calls, any_order=True)


def test_non_default_gpu_and_power() -> None:
    with patch("os.popen") as mock_popen:
        mock_popen.return_value.read.return_value = "NVIDIA GeForce RTX 3080"
        with patch("os.system") as mock_system:
            set_gpu_power_limit_if_needed(gpu_name="NVIDIA GeForce RTX 3080", pw=300)
            calls = [
                mock.call("/usr/bin/sudo /usr/bin/nvidia-smi -pm 1"),
                mock.call("/usr/bin/sudo /usr/bin/nvidia-smi -pl 300"),
            ]
            mock_system.assert_has_calls(calls, any_order=True)


def test_gpu_absence() -> None:
    with patch("os.popen") as mock_popen:
        mock_popen.return_value.read.return_value = "AMD Radeon RX 6900 XT"
        with patch("os.system") as mock_system:
            set_gpu_power_limit_if_needed()
            mock_system.assert_not_called()


def test_command_execution() -> None:
    with patch("os.popen") as mock_popen:
        mock_popen.return_value.read.return_value = "NVIDIA GeForce RTX 3090"
        with patch("os.system") as mock_system:
            set_gpu_power_limit_if_needed(pw=280)
            mock_system.assert_called_with("/usr/bin/sudo /usr/bin/nvidia-smi -pl 280")
