import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import yt_transcripts as yt  # noqa: E402


class VttToTextTest(unittest.TestCase):
    def test_strips_timestamps_tags_and_duplicates(self):
        vtt = (
            "WEBVTT\nKind: captions\nLanguage: ko\n\n"
            "00:00:00.000 --> 00:00:02.000\n안녕하세요<00:00:01.000><c> 여러분</c>\n\n"
            "00:00:02.000 --> 00:00:04.000\n안녕하세요 여러분\n광고 세팅입니다.\n"
        )
        self.assertEqual(yt.vtt_to_text(vtt), "안녕하세요 여러분 광고 세팅입니다.")

    def test_safe_name(self):
        self.assertEqual(yt.safe("쿠팡 광고 교실"), "쿠팡_광고_교실")


if __name__ == "__main__":
    unittest.main()
