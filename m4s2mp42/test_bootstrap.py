import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import ffmpeg_bootstrap


class BootstrapTests(unittest.TestCase):
    def test_extracts_and_validates_ffmpeg_executable(self):
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / "ffmpeg.zip"
            target_path = Path(directory) / "ffmpeg.exe"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr(
                    "ffmpeg-release-essentials/bin/ffmpeg.exe",
                    b"MZ-fixture",
                )

            result = subprocess.CompletedProcess(["ffmpeg"], 0, b"", b"")
            with patch(
                "ffmpeg_bootstrap.subprocess.run", return_value=result
            ) as run:
                ffmpeg_bootstrap._extract_ffmpeg_exe(
                    str(archive_path), str(target_path)
                )

            self.assertEqual(target_path.read_bytes(), b"MZ-fixture")
            run.assert_called_once()

    def test_rejects_archive_without_ffmpeg(self):
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / "bad.zip"
            target_path = Path(directory) / "ffmpeg.exe"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("README.txt", "missing executable")

            with self.assertRaisesRegex(RuntimeError, "未找到 ffmpeg.exe"):
                ffmpeg_bootstrap._extract_ffmpeg_exe(
                    str(archive_path), str(target_path)
                )


if __name__ == "__main__":
    unittest.main()
