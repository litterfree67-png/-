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
    def test_prefix_cleanup_uses_temp_file_and_preserves_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "clip-1-30080.m4s"
            ftyp = b"\x00\x00\x00\x10ftypisom\x00\x00\x00\x00"
            source.write_bytes(b"0" * 9 + ftyp + b"payload")

            cleaned = strip_garbage_prefix(str(source))

            self.assertIsNotNone(cleaned)
            self.assertEqual(Path(cleaned).read_bytes(), ftyp + b"payload")
            os.remove(cleaned)
            self.assertTrue(source.exists())

    def test_prefix_cleanup_leaves_normal_mp4_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "normal.m4s"
            source.write_bytes(b"\x00\x00\x00\x10ftypisom\x00\x00\x00\x00")
            self.assertIsNone(strip_garbage_prefix(str(source)))

    def test_audio_pairing_is_folder_scoped_and_quality_independent(self):
        videos, audios = classify_files([
            os.path.join("folder", "episode-1-30080.m4s"),
            os.path.join("folder", "episode-1-30280.m4s"),
            os.path.join("other", "episode-1-30280.m4s"),
        ])
        self.assertEqual(len(videos), 1)
        self.assertEqual(len(audios), 2)
        self.assertEqual(
            build_audio_index(audios).get(media_key(videos[0])),
            audios[0],
        )

    def test_box_and_crf_validation(self):
        self.assertEqual(parse_delogo_box("8:25:500:95"), (8, 25, 500, 95))
        with self.assertRaises(ValueError):
            parse_delogo_box("8:25:0:95")
        with self.assertRaises(ValueError):
            validate_options(ConversionOptions(crf=52))

    def test_conversion_uses_single_ffmpeg_pass_and_atomic_output(self):
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
            self.assertIn("-c:v", command_seen)
            self.assertIn("copy", command_seen)
            self.assertFalse(any(".partial.mp4" in item for item in os.listdir(directory)))

    def test_prefixed_input_is_cleaned_before_ffmpeg_and_removed_afterward(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "clip-1-30080.m4s"
            ftyp = b"\x00\x00\x00\x10ftypisom\x00\x00\x00\x00"
            source.write_bytes(b"0" * 9 + ftyp + b"payload")
            command_seen = []
            cleaned_path = []

            def fake_run(command, **_kwargs):
                command_seen.extend(command)
                input_path = command[command.index("-i") + 1]
                cleaned_path.append(input_path)
                self.assertEqual(Path(input_path).read_bytes(), ftyp + b"payload")
                Path(command[-1]).write_bytes(b"mp4")
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch("m4s2mp4_core.subprocess.run", side_effect=fake_run):
                convert_file(
                    str(source),
                    directory,
                    ConversionOptions(delogo=False),
                    ffmpeg="ffmpeg",
                )

            self.assertNotEqual(cleaned_path[0], str(source))
            self.assertFalse(os.path.exists(cleaned_path[0]))

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

    def test_failed_conversion_keeps_existing_output_and_cleans_partial(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "clip-1-30080.m4s"
            output = Path(directory) / "clip.mp4"
            source.write_bytes(b"video")
            output.write_bytes(b"keep")
            failed = subprocess.CompletedProcess(["ffmpeg"], 1, "", "fixture error")

            with patch("m4s2mp4_core.subprocess.run", return_value=failed):
                with self.assertRaisesRegex(RuntimeError, "fixture error"):
                    convert_file(
                        str(source),
                        directory,
                        ConversionOptions(delogo=False, overwrite=True),
                        ffmpeg="ffmpeg",
                    )

            self.assertEqual(output.read_bytes(), b"keep")
            self.assertFalse(any(".partial.mp4" in item for item in os.listdir(directory)))


if __name__ == "__main__":
    unittest.main()
