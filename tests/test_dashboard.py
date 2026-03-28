import os
import sys
import unittest
from unittest.mock import patch


ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
SRC_DIR = os.path.join(ROOT_DIR, "src")

if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

try:
    import dashboard
    DASHBOARD_IMPORT_ERROR = None
except ModuleNotFoundError as exc:  # pragma: no cover - depends on local Flask install
    dashboard = None
    DASHBOARD_IMPORT_ERROR = exc


def _sample_image_config() -> dict:
    return {
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
            "checkpoint": "sd_xl_base_1.0_0.9vae.safetensors",
            "negative_prompt": "low quality, blurry",
            "steps": 8,
            "cfg": 4.0,
            "sampler_name": "euler",
            "scheduler": "normal",
            "timeout_seconds": 180,
        },
    }


@unittest.skipIf(dashboard is None, f"dashboard dependencies missing: {DASHBOARD_IMPORT_ERROR}")
class DashboardTests(unittest.TestCase):
    @patch("dashboard._build_service_statuses")
    @patch("dashboard.get_image_generation_config")
    @patch("dashboard.get_active_model")
    @patch("dashboard.get_active_provider")
    @patch("dashboard.get_llm_provider")
    @patch("dashboard.get_cardnews_config")
    @patch("dashboard.get_cardnews_drafts")
    @patch("dashboard.get_accounts")
    @patch("dashboard.get_full_config")
    @patch("dashboard.ensure_config_file")
    def test_dashboard_index_renders_workspace_sections(
        self,
        _ensure_config_file_mock,
        get_full_config_mock,
        get_accounts_mock,
        get_cardnews_drafts_mock,
        get_cardnews_config_mock,
        get_llm_provider_mock,
        get_active_provider_mock,
        get_active_model_mock,
        get_image_generation_config_mock,
        build_service_statuses_mock,
    ) -> None:
        get_full_config_mock.return_value = {
            "llm_provider": "lmstudio",
            "llm_model": "qwen-test",
            "post_bridge": {"enabled": False, "platforms": ["instagram"]},
        }
        get_accounts_mock.side_effect = lambda provider: {
            "youtube": [{"nickname": "YT A", "niche": "finance", "language": "English"}],
            "cardnews": [
                {
                    "id": "profile-1",
                    "nickname": "Finance KR",
                    "niche": "budgeting",
                    "language": "Korean",
                    "channels": ["instagram"],
                }
            ],
        }[provider]
        get_cardnews_drafts_mock.return_value = [
            {
                "id": "draft-1",
                "profile_id": "profile-1",
                "profile_nickname": "Finance KR",
                "topic": "How to save in your 20s",
                "channels": ["instagram"],
                "slides": [{"type": "cover", "title": "How to save in your 20s"}],
                "status": "reviewed",
                "review": {"status": "flag", "summary": "Needs fact check.", "issues": ["Verify number claim."]},
                "created_at": "2026-03-28T03:22:28Z",
                "asset_paths": [],
            }
        ]
        get_cardnews_config_mock.return_value = {
            "slides_per_post": 6,
            "review_required": True,
            "default_channels": ["instagram"],
        }
        get_llm_provider_mock.return_value = "lmstudio"
        get_active_provider_mock.return_value = "lmstudio"
        get_active_model_mock.return_value = "qwen-test"
        get_image_generation_config_mock.return_value = _sample_image_config()
        build_service_statuses_mock.return_value = [
            {"name": "LLM", "kind": "ok", "summary": "LM Studio online", "detail": "qwen-test"},
            {"name": "Image", "kind": "ok", "summary": "ComfyUI online", "detail": "sd_xl_base_1.0_0.9vae.safetensors"},
        ]

        app = dashboard.create_app()
        client = app.test_client()

        response = client.get("/")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("CardNews Studio", html)
        self.assertIn("Compose Workspace", html)
        self.assertIn("Draft Library", html)
        self.assertIn("Stack Settings", html)
        self.assertIn("How to save in your 20s", html)

    @patch("dashboard.update_config")
    @patch("dashboard.get_image_generation_config")
    @patch("dashboard.ensure_config_file")
    def test_apply_image_preset_merges_with_existing_comfyui_config(
        self,
        _ensure_config_file_mock,
        get_image_generation_config_mock,
        update_config_mock,
    ) -> None:
        get_image_generation_config_mock.return_value = _sample_image_config()

        app = dashboard.create_app()
        client = app.test_client()

        response = client.post("/settings/image-preset", data={"preset": "flux_fast"})

        self.assertEqual(response.status_code, 302)
        update_payload = update_config_mock.call_args.args[0]
        self.assertEqual(update_payload["image_generation"]["provider"], "comfyui")
        self.assertEqual(
            update_payload["image_generation"]["comfyui"]["checkpoint"],
            "flux1-schnell-fp8.safetensors",
        )
        self.assertEqual(update_payload["image_generation"]["comfyui"]["base_url"], "http://127.0.0.1:8188")
        self.assertEqual(update_payload["image_generation"]["comfyui"]["steps"], 4)
        self.assertEqual(update_payload["image_generation"]["comfyui"]["cfg"], 1.0)
        self.assertEqual(update_payload["cardnews"]["background_strategy"], "shared_single")


if __name__ == "__main__":
    unittest.main()
