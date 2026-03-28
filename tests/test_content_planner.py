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
            {
              "type": "cover",
              "eyebrow": "START HERE",
              "title": "One",
              "body": "Body 1",
              "highlight": "Cut one leak",
              "bullets": ["Track spending", "Cancel extras"],
              "visual_prompt": "Prompt 1"
            }
          ]
        }
        """

        outline = content_planner.generate_cardnews_outline("Saving money", "Korean", 3)

        self.assertEqual(outline["topic"], "Saving money")
        self.assertEqual(len(outline["slides"]), 3)
        self.assertEqual(outline["slides"][0]["type"], "cover")
        self.assertEqual(outline["slides"][1]["type"], "insight")
        self.assertEqual(outline["slides"][2]["type"], "cta")
        self.assertEqual(outline["slides"][0]["title"], "One")
        self.assertEqual(outline["slides"][0]["highlight"], "Cut one leak")
        self.assertEqual(outline["slides"][0]["bullets"], ["Track spending", "Cancel extras"])

    @patch("content_planner.generate_text")
    def test_generate_poster_outline_normalizes_items(self, generate_text_mock) -> None:
        generate_text_mock.return_value = """
        {
          "topic": "Seoul must see",
          "caption": "A quick visual route",
          "headline": "SEOUL MUST SEE",
          "subheadline": "A one-page visual guide to the city.",
          "items": [
            {
              "label": "Namsan Tower",
              "sublabel": "City skyline icon",
              "visual_prompt": "Tower with trees"
            }
          ]
        }
        """

        outline = content_planner.generate_poster_outline("Seoul must see", "English", 4)

        self.assertEqual(outline["headline"], "SEOUL MUST SEE")
        self.assertEqual(outline["subheadline"], "A one-page visual guide to the city.")
        self.assertEqual(len(outline["items"]), 4)
        self.assertEqual(outline["items"][0]["label"], "Namsan Tower")
        self.assertEqual(outline["items"][0]["visual_prompt"], "Tower with trees")


if __name__ == "__main__":
    unittest.main()
