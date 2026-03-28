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


class CardNewsJobsCacheTests(unittest.TestCase):
    def test_add_and_update_cardnews_job(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            mp_dir = os.path.join(temp_dir, ".mp")
            os.makedirs(mp_dir, exist_ok=True)

            with patch.object(cache, "ROOT_DIR", temp_dir):
                job = {
                    "id": "job-1",
                    "profile_id": "profile-1",
                    "status": "queued",
                    "progress": 5,
                    "created_at": "2026-03-28T00:00:00Z",
                }
                cache.add_cardnews_job(job)

                loaded = cache.get_cardnews_job("job-1")
                self.assertEqual(loaded["status"], "queued")

                updated = cache.update_cardnews_job("job-1", {"status": "running", "progress": 44})
                self.assertEqual(updated["status"], "running")
                self.assertEqual(updated["progress"], 44)

                jobs = cache.get_cardnews_jobs()
                self.assertEqual(len(jobs), 1)
                self.assertEqual(jobs[0]["id"], "job-1")


if __name__ == "__main__":
    unittest.main()
