import os
import sys
import unittest
from unittest.mock import patch


ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
SRC_DIR = os.path.join(ROOT_DIR, "src")

if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import topic_signal_collector


GOOGLE_TRENDS_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:ht="https://trends.google.com/trending/rss" version="2.0">
  <channel>
    <title>Daily Search Trends</title>
    <item>
      <title>inflation relief</title>
      <ht:approx_traffic>200K+</ht:approx_traffic>
      <link>https://trends.google.com/trending/rss?geo=US</link>
      <pubDate>Sat, 28 Mar 2026 06:00:00 -0700</pubDate>
      <ht:news_item>
        <ht:news_item_title>Inflation relief programs gain attention</ht:news_item_title>
        <ht:news_item_url>https://example.com/news/inflation-relief</ht:news_item_url>
        <ht:news_item_source>Example News</ht:news_item_source>
      </ht:news_item>
    </item>
  </channel>
</rss>
"""

RSS_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Example Feed</title>
    <item>
      <title>Inflation tips for families this week</title>
      <description>Practical budgeting guidance for household costs.</description>
      <link>https://example.com/rss/inflation-tips</link>
      <pubDate>Sat, 28 Mar 2026 10:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""


class FakeResponse:
    def __init__(self, *, text: str = "", json_payload: dict | None = None, status_code: int = 200):
        self.text = text
        self._json_payload = json_payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> dict:
        return self._json_payload or {}


class TopicSignalCollectorTests(unittest.TestCase):
    def test_collect_topic_signals_builds_report(self) -> None:
        config_payload = {
            "ttl_minutes": 180,
            "region": "US",
            "language": "en-US",
            "suggestion_count": 3,
            "max_items_per_source": 5,
            "google_trends": {"enabled": True, "rss_url": "", "region": "US"},
            "youtube": {"enabled": False, "api_key": "", "region_code": "US", "video_category_id": "0", "max_results": 5},
            "rss": {"enabled": True, "feeds": ["https://feeds.example.test/rss"], "max_results": 5},
            "reddit": {"enabled": True, "subreddits": ["news"], "sort": "top", "time": "day", "max_results": 5},
            "x": {"enabled": False, "bearer_token": "", "queries": [], "language": "en", "max_results": 5},
        }

        def fake_get(url, headers=None, params=None, timeout=None):
            if "trends.google.com/trending/rss" in url:
                return FakeResponse(text=GOOGLE_TRENDS_RSS)
            if "feeds.example.test/rss" in url:
                return FakeResponse(text=RSS_FEED)
            if "reddit.com/search.json" in url:
                return FakeResponse(
                    json_payload={
                        "data": {
                            "children": [
                                {
                                    "data": {
                                        "title": "Inflation is changing grocery budgets",
                                        "subreddit": "news",
                                        "score": 321,
                                        "num_comments": 45,
                                        "permalink": "/r/news/comments/test/inflation",
                                        "created_utc": 1774692000,
                                    }
                                }
                            ]
                        }
                    }
                )
            raise AssertionError(f"Unexpected URL: {url}")

        with patch("topic_signal_collector.get_topic_signal_config", return_value=config_payload), patch(
            "topic_signal_collector.get_topic_signal_report",
            return_value=None,
        ), patch("topic_signal_collector.save_topic_signal_report") as save_mock, patch(
            "topic_signal_collector.generate_json",
            return_value={
                "topics": [
                    {
                        "topic": "이번 주 생활물가 대응 포인트",
                        "why_now": "Google Trends와 Reddit에서 물가 키워드가 동시에 올라왔습니다.",
                        "source_mix": ["google_trends", "reddit"],
                        "keywords": ["inflation", "budgets"],
                    }
                ]
            },
        ), patch("topic_signal_collector.requests.get", side_effect=fake_get):
            report = topic_signal_collector.collect_topic_signals_for_profile(
                {
                    "id": "profile-1",
                    "nickname": "생활정보",
                    "niche": "inflation, grocery prices",
                    "language": "Korean",
                },
                force_refresh=True,
            )

        self.assertEqual(report["profile_id"], "profile-1")
        self.assertEqual(report["suggestions"][0]["topic"], "이번 주 생활물가 대응 포인트")
        self.assertTrue(any(signal["source"] == "google_trends" for signal in report["signals"]))
        self.assertTrue(any(signal["source"] == "reddit" for signal in report["signals"]))
        self.assertTrue(any(keyword["term"] == "inflation" for keyword in report["keywords"]))
        save_mock.assert_called_once()

    def test_collect_topic_signals_uses_cache_within_ttl(self) -> None:
        cached = {
            "profile_id": "profile-1",
            "updated_at": "2026-03-28T00:00:00Z",
            "suggestions": [{"topic": "Cached topic"}],
        }

        class FrozenDateTime(topic_signal_collector.datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 3, 28, 1, 0, 0, tzinfo=tz or topic_signal_collector.timezone.utc)

        with patch("topic_signal_collector.datetime", FrozenDateTime), patch(
            "topic_signal_collector.get_topic_signal_config",
            return_value={
                "ttl_minutes": 180,
                "region": "US",
                "language": "en-US",
                "suggestion_count": 6,
                "max_items_per_source": 8,
                "google_trends": {"enabled": True, "rss_url": "", "region": "US"},
                "youtube": {"enabled": False, "api_key": "", "region_code": "US", "video_category_id": "0", "max_results": 8},
                "rss": {"enabled": False, "feeds": [], "max_results": 8},
                "reddit": {"enabled": False, "subreddits": [], "sort": "top", "time": "day", "max_results": 8},
                "x": {"enabled": False, "bearer_token": "", "queries": [], "language": "en", "max_results": 8},
            },
        ), patch("topic_signal_collector.get_topic_signal_report", return_value=cached), patch(
            "topic_signal_collector.requests.get"
        ) as requests_get_mock:
            report = topic_signal_collector.collect_topic_signals_for_profile(
                {"id": "profile-1", "niche": "budgeting", "language": "Korean"},
                force_refresh=False,
            )

        self.assertEqual(report["suggestions"][0]["topic"], "Cached topic")
        requests_get_mock.assert_not_called()

    def test_collect_topic_signals_falls_back_when_llm_synthesis_fails(self) -> None:
        config_payload = {
            "ttl_minutes": 180,
            "region": "US",
            "language": "en-US",
            "suggestion_count": 2,
            "max_items_per_source": 5,
            "google_trends": {"enabled": True, "rss_url": "", "region": "US"},
            "youtube": {"enabled": False, "api_key": "", "region_code": "US", "video_category_id": "0", "max_results": 5},
            "rss": {"enabled": False, "feeds": [], "max_results": 5},
            "reddit": {"enabled": False, "subreddits": [], "sort": "top", "time": "day", "max_results": 5},
            "x": {"enabled": False, "bearer_token": "", "queries": [], "language": "en", "max_results": 5},
        }

        with patch("topic_signal_collector.get_topic_signal_config", return_value=config_payload), patch(
            "topic_signal_collector.get_topic_signal_report",
            return_value=None,
        ), patch("topic_signal_collector.save_topic_signal_report"), patch(
            "topic_signal_collector.requests.get",
            return_value=FakeResponse(text=GOOGLE_TRENDS_RSS),
        ), patch(
            "topic_signal_collector.generate_json",
            side_effect=RuntimeError("llm unavailable"),
        ):
            report = topic_signal_collector.collect_topic_signals_for_profile(
                {"id": "profile-1", "niche": "inflation", "language": "Korean"},
                force_refresh=True,
            )

        self.assertTrue(report["suggestions"])
        self.assertEqual(report["suggestions"][0]["topic"], "inflation relief")


if __name__ == "__main__":
    unittest.main()
