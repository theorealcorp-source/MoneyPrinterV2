import os
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
SRC_DIR = os.path.join(ROOT_DIR, "src")

if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from classes.CardNews import CardNews


class CardNewsGenerationStrategyTests(unittest.TestCase):
    @patch("classes.CardNews.update_cardnews_draft")
    @patch("classes.CardNews.render_cardnews_slides")
    @patch("classes.CardNews.generate_image_asset")
    @patch("classes.CardNews.get_cardnews_draft")
    @patch("classes.CardNews.assert_folder_structure")
    @patch("classes.CardNews.get_cardnews_config")
    def test_render_draft_uses_two_background_generations_for_deck_pair(
        self,
        get_cardnews_config_mock,
        _assert_folder_structure_mock,
        get_cardnews_draft_mock,
        generate_image_asset_mock,
        render_cardnews_slides_mock,
        update_cardnews_draft_mock,
    ) -> None:
        get_cardnews_config_mock.return_value = {
            "slides_per_post": 6,
            "review_required": True,
            "default_channels": ["instagram"],
            "render_width": 1080,
            "render_height": 1350,
            "background_strategy": "deck_pair",
            "background_style": "editorial_abstract",
        }
        profile = {
            "id": "profile-1",
            "nickname": "Finance KR",
            "niche": "budgeting",
            "language": "Korean",
            "channels": ["instagram"],
        }
        draft = {
            "id": "draft-1",
            "topic": "Budget reset for office workers",
            "slides": [
                {"type": "cover", "title": "Cover", "visual_prompt": "cover prompt"},
                {"type": "insight", "title": "Insight", "visual_prompt": "insight prompt"},
                {"type": "list", "title": "List", "visual_prompt": "list prompt"},
                {"type": "stat", "title": "Stat", "visual_prompt": "stat prompt"},
                {"type": "quote", "title": "Quote", "visual_prompt": "quote prompt"},
                {"type": "cta", "title": "CTA", "visual_prompt": "cta prompt"},
            ],
        }
        get_cardnews_draft_mock.return_value = draft
        generate_image_asset_mock.side_effect = ["/tmp/hero.png", "/tmp/support.png"]

        with tempfile.TemporaryDirectory() as temp_dir:
            render_cardnews_slides_mock.return_value = [
                os.path.join(temp_dir, f"{index:02d}.png") for index in range(1, 7)
            ]
            update_cardnews_draft_mock.side_effect = lambda _draft_id, payload: payload

            result = CardNews(profile).render_draft("draft-1")

        self.assertEqual(generate_image_asset_mock.call_count, 2)
        slides = result["slides"]
        self.assertEqual(slides[0]["background_path"], "/tmp/hero.png")
        self.assertEqual(slides[1]["background_path"], "/tmp/support.png")
        self.assertEqual(slides[4]["background_path"], "/tmp/hero.png")
        self.assertEqual(slides[5]["background_path"], "/tmp/hero.png")

    @patch("classes.CardNews.update_cardnews_draft")
    @patch("classes.CardNews.render_cardnews_slides")
    @patch("classes.CardNews.generate_image_asset")
    @patch("classes.CardNews.get_cardnews_draft")
    @patch("classes.CardNews.assert_folder_structure")
    @patch("classes.CardNews.get_cardnews_config")
    def test_render_draft_generates_background_and_item_art_for_poster(
        self,
        get_cardnews_config_mock,
        _assert_folder_structure_mock,
        get_cardnews_draft_mock,
        generate_image_asset_mock,
        render_cardnews_slides_mock,
        update_cardnews_draft_mock,
    ) -> None:
        get_cardnews_config_mock.return_value = {
            "format": "poster",
            "slides_per_post": 1,
            "poster_item_count": 4,
            "review_required": True,
            "default_channels": ["instagram"],
            "render_width": 1080,
            "render_height": 1350,
            "background_strategy": "shared_single",
            "background_style": "editorial_abstract",
        }
        profile = {
            "id": "profile-1",
            "nickname": "Travel KR",
            "niche": "travel",
            "language": "English",
            "channels": ["instagram"],
        }
        draft = {
            "id": "draft-1",
            "format": "poster",
            "topic": "Seoul must see",
            "slides": [
                {
                    "type": "poster",
                    "title": "SEOUL MUST SEE",
                    "body": "A one-page visual guide.",
                    "poster_items": [
                        {"label": "Namsan", "sublabel": "Viewpoint", "visual_prompt": "Tower"},
                        {"label": "Kimchi", "sublabel": "Dish", "visual_prompt": "Kimchi bowl"},
                        {"label": "Palace", "sublabel": "Landmark", "visual_prompt": "Palace gate"},
                        {"label": "Bukchon", "sublabel": "Hanok", "visual_prompt": "Hanok homes"},
                    ],
                }
            ],
        }
        get_cardnews_draft_mock.return_value = draft
        generate_image_asset_mock.side_effect = [
            "/tmp/poster-bg.png",
            "/tmp/namsan.png",
            "/tmp/kimchi.png",
            "/tmp/palace.png",
            "/tmp/bukchon.png",
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            render_cardnews_slides_mock.return_value = [os.path.join(temp_dir, "01.png")]
            update_cardnews_draft_mock.side_effect = lambda _draft_id, payload: payload

            result = CardNews(profile).render_draft("draft-1")

        self.assertEqual(generate_image_asset_mock.call_count, 5)
        slide = result["slides"][0]
        self.assertEqual(slide["background_path"], "/tmp/poster-bg.png")
        self.assertEqual(slide["poster_items"][0]["illustration_path"], "/tmp/namsan.png")
        self.assertEqual(slide["poster_items"][3]["illustration_path"], "/tmp/bukchon.png")


if __name__ == "__main__":
    unittest.main()
