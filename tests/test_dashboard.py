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
    @patch("dashboard.get_cardnews_jobs")
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
        get_cardnews_jobs_mock,
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
                "format": "carousel",
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
            "format": "carousel",
            "slides_per_post": 6,
            "poster_item_count": 6,
            "review_required": True,
            "default_channels": ["instagram"],
            "background_strategy": "deck_pair",
            "background_style": "editorial_abstract",
        }
        get_llm_provider_mock.return_value = "lmstudio"
        get_active_provider_mock.return_value = "lmstudio"
        get_active_model_mock.return_value = "qwen-test"
        get_image_generation_config_mock.return_value = _sample_image_config()
        get_cardnews_jobs_mock.return_value = []
        build_service_statuses_mock.return_value = [
            {"name": "LLM", "kind": "ok", "summary": "LM Studio online", "detail": "qwen-test"},
            {
                "name": "Image",
                "kind": "warn",
                "summary": "ComfyUI offline",
                "detail": "sd_xl_base_1.0_0.9vae.safetensors",
                "action_url": "/services/comfyui/start",
                "action_label": "Start ComfyUI",
            },
        ]

        app = dashboard.create_app()
        client = app.test_client()

        response = client.get("/")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("CardNews Studio", html)
        self.assertIn("Compose Workspace", html)
        self.assertIn("Generation Queue", html)
        self.assertIn("Draft Library", html)
        self.assertIn("Stack Settings", html)
        self.assertIn("How to save in your 20s", html)
        self.assertIn("Start ComfyUI", html)

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

    @patch("dashboard._start_comfyui_service")
    @patch("dashboard.get_image_generation_config")
    @patch("dashboard.ensure_config_file")
    def test_start_comfyui_route_starts_service_and_redirects(
        self,
        _ensure_config_file_mock,
        get_image_generation_config_mock,
        start_comfyui_service_mock,
    ) -> None:
        get_image_generation_config_mock.return_value = _sample_image_config()
        start_comfyui_service_mock.return_value = (True, "ComfyUI is online.")

        app = dashboard.create_app()
        client = app.test_client()

        response = client.post("/services/comfyui/start")

        self.assertEqual(response.status_code, 302)
        start_comfyui_service_mock.assert_called_once_with("http://127.0.0.1:8188")

    @patch("dashboard.threading.Thread")
    @patch("dashboard.add_cardnews_job")
    @patch("dashboard.ensure_model_selected")
    @patch("dashboard.get_accounts")
    @patch("dashboard.ensure_config_file")
    def test_generate_cardnews_starts_background_job_and_redirects(
        self,
        _ensure_config_file_mock,
        get_accounts_mock,
        _ensure_model_selected_mock,
        add_cardnews_job_mock,
        thread_mock,
    ) -> None:
        get_accounts_mock.side_effect = lambda provider: {
            "youtube": [],
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

        app = dashboard.create_app()
        client = app.test_client()

        response = client.post(
            "/cardnews/generate",
            data={"profile_id": "profile-1", "topic_override": "Budget habits", "format_mode": "poster"},
        )

        self.assertEqual(response.status_code, 302)
        add_cardnews_job_mock.assert_called_once()
        thread_mock.assert_called_once()
        thread_mock.return_value.start.assert_called_once()

    @patch("dashboard.get_cardnews_draft")
    @patch("dashboard.get_cardnews_jobs")
    @patch("dashboard.ensure_config_file")
    def test_api_jobs_returns_serialized_jobs(
        self,
        _ensure_config_file_mock,
        get_cardnews_jobs_mock,
        get_cardnews_draft_mock,
    ) -> None:
        get_cardnews_jobs_mock.return_value = [
            {
                "id": "job-1",
                "profile_nickname": "Finance KR",
                "topic": "Budget habits",
                "format": "poster",
                "status": "running",
                "stage": "illustrations",
                "progress": 54,
                "message": "Generating poster illustration 2/6",
                "draft_id": "",
                "created_at": "2026-03-28T00:00:00Z",
            }
        ]
        get_cardnews_draft_mock.return_value = None

        app = dashboard.create_app()
        client = app.test_client()

        response = client.get("/api/jobs")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["jobs"][0]["status"], "running")
        self.assertEqual(payload["jobs"][0]["progress"], 54)


if __name__ == "__main__":
    unittest.main()
