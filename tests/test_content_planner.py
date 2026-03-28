import os
import sys
import unittest
from unittest.mock import patch


ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
SRC_DIR = os.path.join(ROOT_DIR, "src")

if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import content_planner


class ContentPlannerTests(unittest.TestCase):
    @patch("content_planner.generate_text")
    def test_generate_json_strips_code_fences(self, generate_text_mock) -> None:
        generate_text_mock.return_value = """```json
        {"topic":"T","caption":"C","slides":[]}
        ```"""

        payload = content_planner.generate_json("prompt")

        self.assertEqual(payload["topic"], "T")
        self.assertEqual(payload["caption"], "C")

    @patch("content_planner.generate_text")
    def test_generate_cardnews_outline_normalizes_slide_count(self, generate_text_mock) -> None:
        generate_text_mock.return_value = """
        {
          "topic": "Saving money",
          "caption": "Simple saving system",
          "slides": [
            {"title": "One", "body": "Body 1", "visual_prompt": "Prompt 1"}
          ]
        }
        """

        outline = content_planner.generate_cardnews_outline("Saving money", "Korean", 3)

        self.assertEqual(outline["topic"], "Saving money")
        self.assertEqual(len(outline["slides"]), 3)
        self.assertEqual(outline["slides"][0]["title"], "One")


if __name__ == "__main__":
    unittest.main()
