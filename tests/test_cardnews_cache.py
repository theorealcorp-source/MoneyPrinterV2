import json
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


class CardNewsCacheTests(unittest.TestCase):
    def test_add_and_update_cardnews_draft(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            mp_dir = os.path.join(temp_dir, ".mp")
            os.makedirs(mp_dir, exist_ok=True)

            with patch.object(cache, "ROOT_DIR", temp_dir):
                draft = {
                    "id": "draft-1",
                    "profile_id": "profile-1",
                    "topic": "Budgeting habits",
                    "created_at": "2026-03-28T00:00:00Z",
                }
                cache.add_cardnews_draft(draft)

                loaded = cache.get_cardnews_draft("draft-1")
                self.assertEqual(loaded["topic"], "Budgeting habits")

                updated = cache.update_cardnews_draft("draft-1", {"status": "approved"})
                self.assertEqual(updated["status"], "approved")

                drafts = cache.get_cardnews_drafts_for_profile("profile-1")
                self.assertEqual(len(drafts), 1)
                self.assertEqual(drafts[0]["status"], "approved")


if __name__ == "__main__":
    unittest.main()
