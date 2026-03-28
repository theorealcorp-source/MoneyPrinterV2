import os
import sys
import tempfile
import unittest
from unittest.mock import patch
from unittest.mock import call


ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
SRC_DIR = os.path.join(ROOT_DIR, "src")

if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import image_generator


class DummyResponse:
    def __init__(self, json_data=None, content=b"", status_code=200):
        self._json_data = json_data
        self.content = content
        self.status_code = status_code

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class ImageGeneratorTests(unittest.TestCase):
    @patch("image_generator.time.sleep", return_value=None)
    @patch("image_generator.requests.get")
    @patch("image_generator.requests.post")
    @patch("image_generator.get_image_generation_config")
    def test_generate_image_asset_with_comfyui_builtin_workflow(
        self,
        get_image_generation_config_mock,
        requests_post_mock,
        requests_get_mock,
        _sleep_mock,
    ) -> None:
        get_image_generation_config_mock.return_value = {
            "provider": "comfyui",
            "gemini": {
                "api_base_url": "https://example.test",
                "api_key": "",
                "model": "gemini-3.1-flash-image-preview",
                "aspect_ratio": "4:5",
            },
            "comfyui": {
                "base_url": "http://127.0.0.1:8188",
                "workflow_path": "",
                "checkpoint": "sd_xl_base_1.0.safetensors",
                "negative_prompt": "low quality, blurry",
                "steps": 8,
                "cfg": 4.0,
                "sampler_name": "euler",
                "scheduler": "normal",
                "timeout_seconds": 30,
            },
        }

        requests_post_mock.return_value = DummyResponse({"prompt_id": "prompt-123"})
        requests_get_mock.side_effect = [
            DummyResponse(
                {
                    "prompt-123": {
                        "outputs": {
                            "7": {
                                "images": [
                                    {
                                        "filename": "test.png",
                                        "subfolder": "MoneyPrinter",
                                        "type": "output",
                                    }
                                ]
                            }
                        }
                    }
                }
            ),
            DummyResponse(content=b"fake-png-bytes"),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = image_generator.generate_image_asset(
                "Editorial illustration of budgeting habits",
                temp_dir,
                aspect_ratio="4:5",
                provider="comfyui",
            )

            self.assertIsNotNone(image_path)
            self.assertTrue(os.path.exists(image_path))
            self.assertGreater(os.path.getsize(image_path), 0)

            prompt_payload = requests_post_mock.call_args.kwargs["json"]["prompt"]
            self.assertEqual(
                prompt_payload["1"]["inputs"]["ckpt_name"],
                "sd_xl_base_1.0.safetensors",
            )
            self.assertEqual(prompt_payload["4"]["inputs"]["width"], 1024)
            self.assertEqual(prompt_payload["4"]["inputs"]["height"], 1280)

    @patch("image_generator._poll_comfyui_history", return_value=None)
    @patch("image_generator.requests.post")
    @patch("image_generator.get_image_generation_config")
    def test_generate_image_asset_with_comfyui_timeout_cancels_prompt_and_records_error(
        self,
        get_image_generation_config_mock,
        requests_post_mock,
        _poll_comfyui_history_mock,
    ) -> None:
        get_image_generation_config_mock.return_value = {
            "provider": "comfyui",
            "gemini": {},
            "comfyui": {
                "base_url": "http://127.0.0.1:8188",
                "workflow_path": "",
                "checkpoint": "flux1-schnell-fp8.safetensors",
                "negative_prompt": "",
                "steps": 4,
                "cfg": 1.0,
                "sampler_name": "euler",
                "scheduler": "simple",
                "timeout_seconds": 360,
            },
        }
        requests_post_mock.side_effect = [
            DummyResponse({"prompt_id": "prompt-123"}),
            DummyResponse({}),
            DummyResponse({}),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = image_generator.generate_image_asset(
                "Poster illustration",
                temp_dir,
                aspect_ratio="1:1",
                provider="comfyui",
            )

        self.assertIsNone(image_path)
        self.assertIn("timed out after 360 seconds", image_generator.get_last_image_generation_error())
        self.assertEqual(
            requests_post_mock.call_args_list,
            [
                call(
                    "http://127.0.0.1:8188/prompt",
                    json=unittest.mock.ANY,
                    timeout=30,
                ),
                call(
                    "http://127.0.0.1:8188/interrupt",
                    json={"prompt_id": "prompt-123"},
                    timeout=10,
                ),
                call(
                    "http://127.0.0.1:8188/queue",
                    json={"delete": ["prompt-123"]},
                    timeout=10,
                ),
            ],
        )

    @patch("image_generator.get_image_generation_config")
    def test_generate_image_asset_with_none_provider_returns_none(
        self,
        get_image_generation_config_mock,
    ) -> None:
        get_image_generation_config_mock.return_value = {
            "provider": "none",
            "gemini": {},
            "comfyui": {},
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = image_generator.generate_image_asset(
                "ignored",
                temp_dir,
                provider="none",
            )

        self.assertIsNone(image_path)


if __name__ == "__main__":
    unittest.main()
