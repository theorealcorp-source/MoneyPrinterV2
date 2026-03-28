import os
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
SRC_DIR = os.path.join(ROOT_DIR, "src")

if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import cache


class TopicSignalCacheTests(unittest.TestCase):
    def test_save_and_replace_topic_signal_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            mp_dir = os.path.join(temp_dir, ".mp")
            os.makedirs(mp_dir, exist_ok=True)

            with patch.object(cache, "ROOT_DIR", temp_dir):
                cache.save_topic_signal_report(
                    {
                        "profile_id": "profile-1",
                        "updated_at": "2026-03-28T00:00:00Z",
                        "suggestions": [{"topic": "One"}],
                    }
                )
                cache.save_topic_signal_report(
                    {
                        "profile_id": "profile-1",
                        "updated_at": "2026-03-28T01:00:00Z",
                        "suggestions": [{"topic": "Two"}],
                    }
                )

                loaded = cache.get_topic_signal_report("profile-1")
                self.assertEqual(loaded["suggestions"][0]["topic"], "Two")
                self.assertEqual(len(cache.get_topic_signal_reports()), 1)


if __name__ == "__main__":
    unittest.main()
