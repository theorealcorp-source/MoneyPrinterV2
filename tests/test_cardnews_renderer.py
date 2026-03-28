import os
import sys
import tempfile
import unittest


ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
SRC_DIR = os.path.join(ROOT_DIR, "src")

if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from cardnews_renderer import render_cardnews_slides


class CardNewsRendererTests(unittest.TestCase):
    def test_render_cardnews_slides_supports_multiple_slide_types(self) -> None:
        slides = [
            {
                "type": "cover",
                "eyebrow": "START HERE",
                "title": "Build a better budget",
                "body": "A calmer carousel needs stronger hierarchy and whitespace.",
                "highlight": "Cleaner rhythm",
                "topic": "Budgeting basics",
            },
            {
                "type": "list",
                "eyebrow": "QUICK CHECK",
                "title": "3 places to trim first",
                "body": "Subscriptions. Delivery fees. Impulse add-ons.",
                "bullets": ["Cancel unused apps", "Cook twice this week", "Sleep on big buys"],
                "topic": "Budgeting basics",
            },
            {
                "type": "cta",
                "eyebrow": "NEXT STEP",
                "title": "Keep only one action",
                "body": "Start with the smallest habit you can repeat this week.",
                "highlight": "Save this post",
                "bullets": ["Pick one habit", "Track it for 7 days", "Review on Sunday"],
                "topic": "Budgeting basics",
            },
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            asset_paths = render_cardnews_slides(slides, temp_dir, 1080, 1350, deck_topic="Budgeting basics")

            self.assertEqual(len(asset_paths), 3)
            for asset_path in asset_paths:
                self.assertTrue(os.path.exists(asset_path))
                self.assertGreater(os.path.getsize(asset_path), 0)

    def test_render_cardnews_slides_supports_poster_layout(self) -> None:
        slides = [
            {
                "type": "poster",
                "eyebrow": "VISUAL GUIDE",
                "title": "SEOUL MUST SEE",
                "body": "A one-page visual guide to the city.",
                "topic": "Seoul must see",
                "poster_items": [
                    {"label": "Namsan Tower", "sublabel": "Skyline view", "illustration_path": ""},
                    {"label": "Kimchi", "sublabel": "Classic side dish", "illustration_path": ""},
                    {"label": "Gyeongbokgung", "sublabel": "Historic palace", "illustration_path": ""},
                    {"label": "Bukchon", "sublabel": "Hanok neighborhood", "illustration_path": ""},
                ],
            }
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            asset_paths = render_cardnews_slides(slides, temp_dir, 1080, 1350, deck_topic="Seoul must see")

            self.assertEqual(len(asset_paths), 1)
            self.assertTrue(os.path.exists(asset_paths[0]))
            self.assertGreater(os.path.getsize(asset_paths[0]), 0)

    def test_render_cardnews_slides_supports_public_service_style(self) -> None:
        slides = [
            {
                "type": "cover",
                "eyebrow": "육아정보",
                "title": "부모가 꼭 알아야 할\n영아수당 핵심 정리",
                "body": "지원 범위와 실질 혜택을 한 번에 살펴봅니다.",
                "highlight": "0-1세 지원 제도",
                "topic": "영아수당 가이드",
            },
            {
                "type": "insight",
                "eyebrow": "핵심 비교",
                "title": "국가별 육아정책 차이",
                "body": "한 화면에서 차이를 읽기 쉽게 정리합니다.",
                "topic": "영아수당 가이드",
            },
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            asset_paths = render_cardnews_slides(
                slides,
                temp_dir,
                1080,
                1350,
                deck_topic="영아수당 가이드",
                visual_style="public_service_flat",
            )

            self.assertEqual(len(asset_paths), 2)
            for asset_path in asset_paths:
                self.assertTrue(os.path.exists(asset_path))
                self.assertGreater(os.path.getsize(asset_path), 0)


if __name__ == "__main__":
    unittest.main()
