import os
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
SRC_DIR = os.path.join(ROOT_DIR, "src")

if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from post_bridge_integration import publish_cardnews_images


class CardNewsPublishTests(unittest.TestCase):
    @patch("post_bridge_integration.PostBridge")
    @patch("post_bridge_integration.get_post_bridge_config")
    def test_publish_cardnews_images_uploads_all_assets(
        self,
        get_config_mock,
        post_bridge_cls_mock,
    ) -> None:
        get_config_mock.return_value = {
            "enabled": True,
            "api_key": "token",
            "platforms": ["instagram"],
            "account_ids": [12],
            "auto_crosspost": True,
        }
        client = post_bridge_cls_mock.return_value
        client.upload_media.side_effect = ["media-1", "media-2"]
        client.create_post.return_value = {"id": "post-123", "warnings": []}

        with tempfile.NamedTemporaryFile(suffix=".png") as first, tempfile.NamedTemporaryFile(
            suffix=".png"
        ) as second:
            result = publish_cardnews_images(
                image_paths=[first.name, second.name],
                caption="Carousel caption",
                interactive=False,
                platforms=["instagram"],
            )

        self.assertTrue(result)
        self.assertEqual(client.upload_media.call_count, 2)
        client.create_post.assert_called_once_with(
            caption="Carousel caption",
            social_account_ids=[12],
            media_ids=["media-1", "media-2"],
            platform_configurations=None,
            processing_enabled=False,
        )


if __name__ == "__main__":
    unittest.main()
