import os
import sys
import unittest
from unittest.mock import Mock
from unittest.mock import patch


ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
SRC_DIR = os.path.join(ROOT_DIR, "src")

if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import llm_provider


class LlmProviderTests(unittest.TestCase):
    @patch("llm_provider.requests.get")
    @patch("llm_provider.get_openai_base_url", return_value="http://127.0.0.1:1234/v1")
    @patch("llm_provider.get_openai_api_key", return_value="lm-studio")
    def test_list_models_openai_compatible(
        self,
        _api_key_mock,
        _base_url_mock,
        requests_get_mock,
    ) -> None:
        response = Mock()
        response.json.return_value = {
            "data": [
                {"id": "model-b"},
                {"id": "model-a"},
            ]
        }
        response.raise_for_status.return_value = None
        requests_get_mock.return_value = response

        models = llm_provider.list_models("lmstudio")

        self.assertEqual(models, ["model-a", "model-b"])

    @patch("llm_provider.requests.post")
    @patch("llm_provider.get_openai_base_url", return_value="http://127.0.0.1:1234/v1")
    @patch("llm_provider.get_openai_api_key", return_value="lm-studio")
    def test_generate_text_openai_compatible(
        self,
        _api_key_mock,
        _base_url_mock,
        requests_post_mock,
    ) -> None:
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [
                {"message": {"content": "hello from lm studio"}}
            ]
        }
        requests_post_mock.return_value = response

        llm_provider.select_provider_model("lmstudio", "model-a")
        content = llm_provider.generate_text("hello", provider_name="lmstudio")

        self.assertEqual(content, "hello from lm studio")


if __name__ == "__main__":
    unittest.main()
