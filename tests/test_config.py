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

import config


class PostBridgeConfigTests(unittest.TestCase):
    def write_config(self, directory: str, payload: dict) -> None:
        with open(os.path.join(directory, "config.json"), "w", encoding="utf-8") as handle:
            json.dump(payload, handle)

    def patch_config_paths(self, directory: str):
        return patch.multiple(
            config,
            ROOT_DIR=directory,
            CONFIG_PATH=os.path.join(directory, "config.json"),
            CONFIG_EXAMPLE_PATH=os.path.join(directory, "config.example.json"),
        )

    def test_missing_platforms_uses_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            self.write_config(temp_dir, {"post_bridge": {"enabled": True}})

            with self.patch_config_paths(temp_dir):
                post_bridge_config = config.get_post_bridge_config()

        self.assertEqual(post_bridge_config["platforms"], ["tiktok", "instagram"])

    def test_invalid_or_empty_platforms_do_not_expand_to_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            self.write_config(
                temp_dir,
                {
                    "post_bridge": {
                        "enabled": True,
                        "platforms": ["youtube", "tik-tok"],
                    }
                },
            )

            with self.patch_config_paths(temp_dir):
                post_bridge_config = config.get_post_bridge_config()

        self.assertEqual(post_bridge_config["platforms"], [])

    def test_non_list_platforms_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            self.write_config(
                temp_dir,
                {
                    "post_bridge": {
                        "enabled": True,
                        "platforms": "tiktok",
                    }
                },
            )

            with self.patch_config_paths(temp_dir):
                post_bridge_config = config.get_post_bridge_config()

        self.assertEqual(post_bridge_config["platforms"], [])

    def test_non_object_post_bridge_config_falls_back_to_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            self.write_config(
                temp_dir,
                {
                    "post_bridge": None,
                },
            )

            with self.patch_config_paths(temp_dir):
                post_bridge_config = config.get_post_bridge_config()

        self.assertEqual(post_bridge_config["platforms"], ["tiktok", "instagram"])
        self.assertEqual(post_bridge_config["account_ids"], [])
        self.assertFalse(post_bridge_config["enabled"])

    def test_image_generation_defaults_and_invalid_provider(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            self.write_config(
                temp_dir,
                {
                    "image_generation": {
                        "provider": "unsupported",
                        "comfyui": {
                            "steps": "oops",
                            "cfg": "bad",
                        },
                    }
                },
            )

            with self.patch_config_paths(temp_dir):
                image_config = config.get_image_generation_config()

        self.assertEqual(image_config["provider"], "gemini")
        self.assertEqual(image_config["comfyui"]["steps"], 8)
        self.assertEqual(image_config["comfyui"]["cfg"], 4.0)

    def test_cardnews_background_defaults_and_invalid_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            self.write_config(
                temp_dir,
                {
                    "cardnews": {
                        "format": "weird-mode",
                        "poster_item_count": "oops",
                        "background_strategy": "something-weird",
                        "background_style": "broken-style",
                    }
                },
            )

            with self.patch_config_paths(temp_dir):
                cardnews_config = config.get_cardnews_config()

        self.assertEqual(cardnews_config["format"], "carousel")
        self.assertEqual(cardnews_config["poster_item_count"], 6)
        self.assertEqual(cardnews_config["background_strategy"], "deck_pair")
        self.assertEqual(cardnews_config["background_style"], "editorial_abstract")

    def test_cardnews_accepts_public_service_background_style(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            self.write_config(
                temp_dir,
                {
                    "cardnews": {
                        "background_style": "public_service_flat",
                    }
                },
            )

            with self.patch_config_paths(temp_dir):
                cardnews_config = config.get_cardnews_config()

        self.assertEqual(cardnews_config["background_style"], "public_service_flat")

    def test_topic_signal_config_uses_defaults_and_env_fallbacks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            self.write_config(
                temp_dir,
                {
                    "topic_signals": {
                        "ttl_minutes": "oops",
                        "youtube": {"enabled": True},
                        "x": {"enabled": True},
                    }
                },
            )

            with patch.dict(
                os.environ,
                {"YOUTUBE_API_KEY": "yt-env-key", "X_BEARER_TOKEN": "x-env-token"},
                clear=False,
            ):
                with self.patch_config_paths(temp_dir):
                    signal_config = config.get_topic_signal_config()

        self.assertEqual(signal_config["ttl_minutes"], 180)
        self.assertEqual(signal_config["youtube"]["api_key"], "yt-env-key")
        self.assertEqual(signal_config["x"]["bearer_token"], "x-env-token")
        self.assertEqual(signal_config["rss"]["feeds"][0], "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en")

    def test_root_dir_is_repo_root_from_file_location(self) -> None:
        expected_root = ROOT_DIR
        self.assertEqual(config.ROOT_DIR, expected_root)


if __name__ == "__main__":
    unittest.main()
