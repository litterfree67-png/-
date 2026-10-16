import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from m4s2mp4_core import (
    ConversionOptions,
    build_audio_index,
    classify_files,
    convert_file,
    media_key,
    parse_delogo_box,
    strip_garbage_prefix,
    validate_options,
)


class CoreTests(unittest.TestCase):
    def test_prefix_cleanup_preserves_media_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "clip-1-30080.m4s"
            ftyp = b"\x00\x00\x00\x10ftypisom\x00\x00\x00\x00"
            source.write_bytes(b"0" * 9 + ftyp + b"payload")

            cleaned = strip_garbage_prefix(str(source))

            self.assertIsNotNone(cleaned)
            self.assertEqual(Path(cleaned).read_bytes(), ftyp + b"payload")
            os.remove(cleaned)

    def test_normal_mp4_needs_no_prefix_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "normal.m4s"
            source.write_bytes(b"\x00\x00\x00\x10ftypisom\x00\x00\x00\x00")
            self.assertIsNone(strip_garbage_prefix(str(source)))

    def test_audio_pairing_is_scoped_to_the_source_folder(self):
        paths = [
            os.path.join("one", "episode-1-30080.m4s"),
            os.path.join("one", "episode-1-30280.m4s"),
            os.path.join("two", "episode-1-30280.m4s"),
        ]
        videos, audios = classify_files(paths)
        index = build_audio_index(audios)
        self.assertEqual(index.get(media_key(videos[0])), audios[0])

    def test_option_validation(self):
        self.assertEqual(parse_delogo_box("8:25:500:95"), (8, 25, 500, 95))
        with self.assertRaises(ValueError):
            parse_delogo_box("8:25:0:95")
        with self.assertRaises(ValueError):
            validate_options(ConversionOptions(crf=52))

    def test_conversion_uses_atomic_temporary_output(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "clip-1-30080.m4s"
            source.write_bytes(b"video")
            command_seen = []

            def fake_run(command, **_kwargs):
                command_seen.extend(command)
                Path(command[-1]).write_bytes(b"mp4")
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch("m4s2mp4_core.subprocess.run", side_effect=fake_run):
                output = convert_file(
                    str(source),
                    directory,
                    ConversionOptions(delogo=False),
                    ffmpeg="ffmpeg",
                )

            self.assertEqual(Path(output).read_bytes(), b"mp4")
            self.assertIn("copy", command_seen)
            self.assertFalse(
                any(".partial.mp4" in name for name in os.listdir(directory))
            )

    def test_existing_output_is_not_overwritten_by_default(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "clip-1-30080.m4s"
            output = Path(directory) / "clip.mp4"
            source.write_bytes(b"video")
            output.write_bytes(b"keep")

            with patch("m4s2mp4_core.subprocess.run") as run:
                result = convert_file(
                    str(source),
                    directory,
                    ConversionOptions(delogo=False),
                    ffmpeg="ffmpeg",
                )

            self.assertIsNone(result)
            self.assertEqual(output.read_bytes(), b"keep")
            run.assert_not_called()

    def test_failed_conversion_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "clip-1-30080.m4s"
            output = Path(directory) / "clip.mp4"
            source.write_bytes(b"video")
            output.write_bytes(b"keep")
            failed = subprocess.CompletedProcess(
                ["ffmpeg"], 1, "", "fixture error"
            )

            with patch("m4s2mp4_core.subprocess.run", return_value=failed):
                with self.assertRaisesRegex(RuntimeError, "fixture error"):
                    convert_file(
                        str(source),
                        directory,
                        ConversionOptions(delogo=False, overwrite=True),
                        ffmpeg="ffmpeg",
                    )

            self.assertEqual(output.read_bytes(), b"keep")
            self.assertFalse(
                any(".partial.mp4" in name for name in os.listdir(directory))
            )


if __name__ == "__main__":
    unittest.main()
