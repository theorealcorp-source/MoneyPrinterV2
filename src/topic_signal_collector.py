import email.utils
import json
import re
import xml.etree.ElementTree as ET

from datetime import datetime
from datetime import timedelta
from datetime import timezone
from urllib.parse import quote_plus

import requests

from cache import get_topic_signal_report
from cache import save_topic_signal_report
from config import get_topic_signal_config
from content_planner import generate_json
from status import info
from status import warning


DEFAULT_TIMEOUT = 30
DEFAULT_HEADERS = {
    "User-Agent": "MoneyPrinterV2/1.0 (+https://github.com/FujiwaraChoki/MoneyPrinterV2)",
}
TOKEN_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9'&/-]{2,}|[0-9]+(?:\.[0-9]+)?%|[가-힣]{2,}")
STOPWORDS = {
    "about",
    "after",
    "again",
    "against",
    "around",
    "because",
    "between",
    "could",
    "first",
    "from",
    "have",
    "into",
    "just",
    "more",
    "news",
    "only",
    "over",
    "people",
    "still",
    "than",
    "that",
    "their",
    "there",
    "these",
    "they",
    "this",
    "those",
    "today",
    "want",
    "what",
    "when",
    "where",
    "will",
    "with",
    "your",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp() -> str:
    return _utc_now().replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize_text(value: str | None) -> str:
    return " ".join(str(value or "").strip().split())


def _strip_namespace(tag: str) -> str:
    if "}" in str(tag):
        return str(tag).split("}", 1)[1]
    return str(tag)


def _isoformat_from_value(raw_value) -> str:
    if raw_value in (None, ""):
        return ""

    if isinstance(raw_value, (int, float)):
        return datetime.fromtimestamp(float(raw_value), tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    normalized = _normalize_text(raw_value)
    if not normalized:
        return ""

    try:
        if normalized.endswith("Z"):
            parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
        else:
            parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    except ValueError:
        pass

    try:
        parsed = email.utils.parsedate_to_datetime(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    except (TypeError, ValueError):
        return ""


def _traffic_to_score(raw_value: str) -> float:
    normalized = _normalize_text(raw_value).upper().replace(",", "")
    if not normalized:
        return 0.0

    multiplier = 1.0
    if normalized.endswith("K+"):
        multiplier = 1_000.0
        normalized = normalized[:-2]
    elif normalized.endswith("M+"):
        multiplier = 1_000_000.0
        normalized = normalized[:-2]
    elif normalized.endswith("B+"):
        multiplier = 1_000_000_000.0
        normalized = normalized[:-2]
    elif normalized.endswith("+"):
        normalized = normalized[:-1]

    digits = re.sub(r"[^0-9.]", "", normalized)
    try:
        return float(digits) * multiplier if digits else 0.0
    except ValueError:
        return 0.0


def _extract_query_terms(niche: str, extra_terms: list[str] | None = None) -> list[str]:
    candidates = []
    raw_parts = re.split(r"[,/|]|(?:\s{2,})", str(niche or ""))
    for raw_part in raw_parts:
        normalized = _normalize_text(raw_part)
        if normalized and normalized not in candidates:
            candidates.append(normalized)

    if extra_terms:
        for item in extra_terms:
            normalized = _normalize_text(item)
            if normalized and normalized not in candidates:
                candidates.append(normalized)

    if not candidates:
        return []

    short_terms = []
    for candidate in candidates:
        if len(candidate) <= 40:
            short_terms.append(candidate)

    return short_terms[:4] or candidates[:2]


def _signal_sort_key(signal: dict) -> tuple[float, str]:
    return (float(signal.get("score", 0.0)), str(signal.get("published_at", "")))


def _dedupe_signals(signals: list[dict]) -> list[dict]:
    unique = {}

    for signal in sorted(signals, key=_signal_sort_key, reverse=True):
        raw_key = signal.get("url") or signal.get("title") or signal.get("keyword")
        key = _normalize_text(raw_key).lower()
        if not key:
            continue
        if key not in unique:
            unique[key] = signal

    return list(unique.values())


def _recentness_weight(published_at: str) -> float:
    if not published_at:
        return 0.0

    try:
        parsed = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    except ValueError:
        return 0.0

    age = _utc_now() - parsed.astimezone(timezone.utc)
    if age <= timedelta(hours=12):
        return 3.0
    if age <= timedelta(days=1):
        return 2.0
    if age <= timedelta(days=3):
        return 1.0
    return 0.0


def _keyword_tokens(text: str) -> list[str]:
    tokens = []
    for token in TOKEN_PATTERN.findall(str(text or "")):
        normalized = token.strip().lower()
        if not normalized or normalized in STOPWORDS or len(normalized) < 2:
            continue
        tokens.append(normalized)
    return tokens


def _summarize_keywords(signals: list[dict], limit: int = 12) -> list[dict]:
    weighted_terms = {}

    for signal in signals:
        signal_weight = max(1.0, float(signal.get("score", 0.0)) / 100_000.0)
        source = str(signal.get("source", "")).strip()
        keyword_blob = " ".join(
            part
            for part in [
                str(signal.get("keyword", "")),
                str(signal.get("title", "")),
                str(signal.get("summary", "")),
            ]
            if str(part).strip()
        )

        for token in _keyword_tokens(keyword_blob):
            bucket = weighted_terms.setdefault(
                token,
                {
                    "term": token,
                    "score": 0.0,
                    "sources": set(),
                },
            )
            bucket["score"] += signal_weight
            bucket["sources"].add(source)

    ranked = sorted(
        weighted_terms.values(),
        key=lambda item: (item["score"], len(item["sources"]), item["term"]),
        reverse=True,
    )

    return [
        {
            "term": item["term"],
            "score": round(item["score"], 2),
            "sources": sorted(item["sources"]),
        }
        for item in ranked[:limit]
    ]


def _build_fallback_suggestions(
    signals: list[dict],
    niche: str,
    language: str,
    suggestion_count: int,
) -> list[dict]:
    suggestions = []
    seen_topics = set()

    for signal in sorted(signals, key=_signal_sort_key, reverse=True):
        base_topic = _normalize_text(signal.get("keyword") or signal.get("title"))
        if not base_topic:
            continue

        topic = base_topic[:72]
        lowered = topic.lower()
        if lowered in seen_topics:
            continue

        seen_topics.add(lowered)
        suggestions.append(
            {
                "topic": topic,
                "why_now": _normalize_text(signal.get("summary"))
                or f"Emerging signal from {signal.get('source', 'signals')}.",
                "source_mix": [str(signal.get("source", "")).strip()],
                "keywords": [token["term"] for token in _summarize_keywords([signal], limit=3)],
            }
        )

        if len(suggestions) == suggestion_count:
            break

    if suggestions:
        return suggestions

    fallback_topic = _normalize_text(niche) or "Timely topic"
    return [
        {
            "topic": fallback_topic[:72],
            "why_now": f"No source signals were available, so the niche '{fallback_topic}' was used directly.",
            "source_mix": [],
            "keywords": [fallback_topic],
        }
    ]


def _request_json(url: str, *, headers: dict | None = None, params: dict | None = None) -> dict:
    response = requests.get(
        url,
        headers=headers or DEFAULT_HEADERS,
        params=params,
        timeout=DEFAULT_TIMEOUT,
    )
    response.raise_for_status()
    body = response.json()
    return body if isinstance(body, dict) else {}


def _collect_google_trends(config: dict, limit: int) -> list[dict]:
    google_trends = config["google_trends"]
    if not google_trends.get("enabled"):
        return []

    rss_url = str(google_trends.get("rss_url", "")).strip()
    if not rss_url:
        rss_url = (
            "https://trends.google.com/trending/rss"
            f"?geo={quote_plus(str(google_trends.get('region', config['region'])))}"
        )

    response = requests.get(rss_url, headers=DEFAULT_HEADERS, timeout=DEFAULT_TIMEOUT)
    response.raise_for_status()
    root = ET.fromstring(response.text)

    namespace = {"ht": "https://trends.google.com/trending/rss"}
    signals = []

    for item in root.findall("./channel/item")[:limit]:
        trend_title = _normalize_text(item.findtext("title"))
        approx_traffic = _normalize_text(item.findtext("ht:approx_traffic", "", namespace))
        published_at = _isoformat_from_value(item.findtext("pubDate"))

        news_items = []
        for news_item in item.findall("ht:news_item", namespace):
            news_title = _normalize_text(news_item.findtext("ht:news_item_title", "", namespace))
            news_url = _normalize_text(news_item.findtext("ht:news_item_url", "", namespace))
            news_source = _normalize_text(news_item.findtext("ht:news_item_source", "", namespace))
            if news_title:
                news_items.append(
                    {
                        "title": news_title,
                        "url": news_url,
                        "source": news_source,
                    }
                )

        headline = news_items[0]["title"] if news_items else trend_title
        link = news_items[0]["url"] if news_items else _normalize_text(item.findtext("link"))
        summary = " | ".join(news["title"] for news in news_items[:2])

        signals.append(
            {
                "source": "google_trends",
                "signal_type": "trend",
                "keyword": trend_title,
                "title": headline or trend_title,
                "summary": summary,
                "url": link,
                "published_at": published_at,
                "score": _traffic_to_score(approx_traffic),
                "score_label": approx_traffic,
                "meta": {
                    "picture_source": _normalize_text(
                        item.findtext("ht:picture_source", "", namespace)
                    ),
                    "news_items": news_items[:3],
                    "region": str(google_trends.get("region", config["region"])).strip(),
                },
            }
        )

    return signals


def _collect_youtube(config: dict, limit: int) -> list[dict]:
    youtube = config["youtube"]
    if not youtube.get("enabled") or not youtube.get("api_key"):
        return []

    response = requests.get(
        "https://www.googleapis.com/youtube/v3/videos",
        headers=DEFAULT_HEADERS,
        params={
            "part": "snippet,statistics",
            "chart": "mostPopular",
            "regionCode": youtube.get("region_code", config["region"]),
            "videoCategoryId": youtube.get("video_category_id", "0"),
            "maxResults": min(int(youtube.get("max_results", limit)), limit),
            "key": youtube["api_key"],
        },
        timeout=DEFAULT_TIMEOUT,
    )
    response.raise_for_status()
    body = response.json()

    signals = []
    for item in body.get("items", []):
        snippet = item.get("snippet", {})
        stats = item.get("statistics", {})
        title = _normalize_text(snippet.get("title"))
        if not title:
            continue

        view_count = int(stats.get("viewCount", 0) or 0)
        like_count = int(stats.get("likeCount", 0) or 0)
        comment_count = int(stats.get("commentCount", 0) or 0)
        score = float(view_count) + (like_count * 20.0) + (comment_count * 50.0)
        video_id = _normalize_text(item.get("id"))

        signals.append(
            {
                "source": "youtube",
                "signal_type": "video",
                "keyword": title,
                "title": title,
                "summary": _normalize_text(snippet.get("channelTitle")),
                "url": f"https://www.youtube.com/watch?v={video_id}" if video_id else "",
                "published_at": _isoformat_from_value(snippet.get("publishedAt")),
                "score": score,
                "score_label": f"{view_count:,} views",
                "meta": {
                    "channel_title": _normalize_text(snippet.get("channelTitle")),
                    "category_id": _normalize_text(snippet.get("categoryId")),
                    "view_count": view_count,
                    "like_count": like_count,
                    "comment_count": comment_count,
                },
            }
        )

    return signals[:limit]


def _parse_rss_entries(feed_xml: str) -> tuple[str, list[dict]]:
    root = ET.fromstring(feed_xml)
    root_tag = _strip_namespace(root.tag)

    if root_tag == "rss":
        channel = root.find("channel")
        feed_title = _normalize_text(channel.findtext("title")) if channel is not None else ""
        items = []
        for item in channel.findall("item") if channel is not None else []:
            items.append(
                {
                    "title": _normalize_text(item.findtext("title")),
                    "description": _normalize_text(item.findtext("description")),
                    "link": _normalize_text(item.findtext("link")),
                    "published_at": _isoformat_from_value(item.findtext("pubDate")),
                    "categories": [
                        _normalize_text(category.text)
                        for category in item.findall("category")
                        if _normalize_text(category.text)
                    ],
                }
            )
        return feed_title, items

    if root_tag == "feed":
        feed_title = _normalize_text(root.findtext("{*}title"))
        entries = []
        for entry in root.findall("{*}entry"):
            link_value = ""
            link_node = entry.find("{*}link")
            if link_node is not None:
                link_value = _normalize_text(link_node.attrib.get("href"))
            entries.append(
                {
                    "title": _normalize_text(entry.findtext("{*}title")),
                    "description": _normalize_text(
                        entry.findtext("{*}summary") or entry.findtext("{*}content")
                    ),
                    "link": link_value,
                    "published_at": _isoformat_from_value(
                        entry.findtext("{*}published") or entry.findtext("{*}updated")
                    ),
                    "categories": [
                        _normalize_text(category.attrib.get("term"))
                        for category in entry.findall("{*}category")
                        if _normalize_text(category.attrib.get("term"))
                    ],
                }
            )
        return feed_title, entries

    return "", []


def _match_query_terms(text: str, query_terms: list[str]) -> list[str]:
    haystack = _normalize_text(text).lower()
    matches = []
    for term in query_terms:
        normalized = _normalize_text(term).lower()
        if normalized and normalized in haystack and term not in matches:
            matches.append(term)
    return matches


def _collect_rss(config: dict, query_terms: list[str], limit: int) -> list[dict]:
    rss_config = config["rss"]
    if not rss_config.get("enabled"):
        return []

    signals = []
    per_feed_limit = max(3, min(limit, int(rss_config.get("max_results", limit))))

    for feed_url in rss_config.get("feeds", []):
        try:
            response = requests.get(feed_url, headers=DEFAULT_HEADERS, timeout=DEFAULT_TIMEOUT)
            response.raise_for_status()
            feed_title, entries = _parse_rss_entries(response.text)
        except Exception as exc:
            warning(f"Topic signal RSS fetch failed for {feed_url}: {exc}", False)
            continue

        for entry in entries[:per_feed_limit]:
            title = _normalize_text(entry.get("title"))
            description = _normalize_text(entry.get("description"))
            if not title:
                continue

            matched_terms = _match_query_terms(f"{title} {description}", query_terms)
            if query_terms and not matched_terms:
                continue

            score = float(len(matched_terms) * 1000) + _recentness_weight(entry.get("published_at", ""))
            if not matched_terms:
                score = 1.0 + _recentness_weight(entry.get("published_at", ""))

            signals.append(
                {
                    "source": "rss",
                    "signal_type": "article",
                    "keyword": matched_terms[0] if matched_terms else title,
                    "title": title,
                    "summary": description[:220],
                    "url": _normalize_text(entry.get("link")),
                    "published_at": _normalize_text(entry.get("published_at")),
                    "score": score,
                    "score_label": feed_title or "RSS",
                    "meta": {
                        "feed_title": feed_title,
                        "categories": entry.get("categories", []),
                        "matched_terms": matched_terms,
                    },
                }
            )

    return sorted(signals, key=_signal_sort_key, reverse=True)[:limit]


def _collect_reddit(config: dict, query_terms: list[str], limit: int) -> list[dict]:
    reddit = config["reddit"]
    if not reddit.get("enabled"):
        return []

    signals = []
    max_results = min(int(reddit.get("max_results", limit)), limit)

    def _append_posts(payload: dict, query_label: str = "", subreddit_hint: str = "") -> None:
        listing = payload.get("data", {})
        for child in listing.get("children", []):
            post = child.get("data", {})
            title = _normalize_text(post.get("title"))
            if not title:
                continue

            subreddit_name = _normalize_text(post.get("subreddit") or subreddit_hint)
            score_value = int(post.get("score", 0) or 0)
            comments = int(post.get("num_comments", 0) or 0)
            signals.append(
                {
                    "source": "reddit",
                    "signal_type": "post",
                    "keyword": query_label or title,
                    "title": title,
                    "summary": subreddit_name,
                    "url": f"https://www.reddit.com{post.get('permalink', '')}" if post.get("permalink") else "",
                    "published_at": _isoformat_from_value(post.get("created_utc")),
                    "score": float(score_value + (comments * 3)),
                    "score_label": f"{score_value} score / {comments} comments",
                    "meta": {
                        "subreddit": subreddit_name,
                        "num_comments": comments,
                        "query": query_label,
                    },
                }
            )

    if query_terms:
        for term in query_terms[:3]:
            payload = _request_json(
                "https://www.reddit.com/search.json",
                params={
                    "q": term,
                    "sort": reddit.get("sort", "top"),
                    "t": reddit.get("time", "day"),
                    "limit": max_results,
                },
            )
            _append_posts(payload, query_label=term)
    else:
        for subreddit in reddit.get("subreddits", [])[:3]:
            payload = _request_json(
                f"https://www.reddit.com/r/{quote_plus(subreddit)}/{reddit.get('sort', 'top')}.json",
                params={
                    "t": reddit.get("time", "day"),
                    "limit": max_results,
                },
            )
            _append_posts(payload, subreddit_hint=subreddit)

    return _dedupe_signals(signals)[:limit]


def _collect_x(config: dict, query_terms: list[str], limit: int) -> list[dict]:
    x_config = config["x"]
    if not x_config.get("enabled") or not x_config.get("bearer_token"):
        return []

    queries = x_config.get("queries") or query_terms
    queries = [query for query in queries if _normalize_text(query)]
    if not queries:
        return []

    signals = []
    max_results = min(int(x_config.get("max_results", limit)), 10, limit)

    for query in queries[:3]:
        response = requests.get(
            "https://api.x.com/2/tweets/search/recent",
            headers={
                "Authorization": f"Bearer {x_config['bearer_token']}",
                "Content-Type": "application/json",
            },
            params={
                "query": f"{query} lang:{x_config.get('language', 'en')} -is:retweet",
                "max_results": max_results,
                "tweet.fields": "created_at,public_metrics",
            },
            timeout=DEFAULT_TIMEOUT,
        )
        response.raise_for_status()
        body = response.json()

        for item in body.get("data", []):
            text = _normalize_text(item.get("text"))
            if not text:
                continue

            metrics = item.get("public_metrics", {})
            like_count = int(metrics.get("like_count", 0) or 0)
            retweet_count = int(metrics.get("retweet_count", 0) or 0)
            reply_count = int(metrics.get("reply_count", 0) or 0)
            quote_count = int(metrics.get("quote_count", 0) or 0)
            score = float(
                like_count
                + (retweet_count * 3)
                + (reply_count * 2)
                + (quote_count * 2)
            )

            signals.append(
                {
                    "source": "x",
                    "signal_type": "post",
                    "keyword": query,
                    "title": text[:220],
                    "summary": f"X recent search for '{query}'",
                    "url": f"https://x.com/i/web/status/{item.get('id')}" if item.get("id") else "",
                    "published_at": _isoformat_from_value(item.get("created_at")),
                    "score": score,
                    "score_label": f"{like_count} likes / {retweet_count} reposts",
                    "meta": {
                        "query": query,
                        "public_metrics": metrics,
                    },
                }
            )

    return _dedupe_signals(signals)[:limit]


def _build_source_summary(signals: list[dict]) -> list[dict]:
    summary = {}
    for signal in signals:
        bucket = summary.setdefault(
            signal["source"],
            {"source": signal["source"], "count": 0, "top_score": 0.0},
        )
        bucket["count"] += 1
        bucket["top_score"] = max(bucket["top_score"], float(signal.get("score", 0.0)))

    return sorted(summary.values(), key=lambda item: item["count"], reverse=True)


def _build_topic_suggestions(
    signals: list[dict],
    niche: str,
    language: str,
    suggestion_count: int,
) -> list[dict]:
    if not signals:
        return _build_fallback_suggestions(signals, niche, language, suggestion_count)

    compact_signals = [
        {
            "source": signal.get("source"),
            "keyword": signal.get("keyword"),
            "title": signal.get("title"),
            "summary": signal.get("summary"),
            "score_label": signal.get("score_label"),
        }
        for signal in signals[:18]
    ]

    prompt = f"""
You are turning live topic signals into social-media card-news topic ideas.
Return only valid JSON with this exact shape:
{{
  "topics": [
    {{
      "topic": "string",
      "why_now": "string",
      "source_mix": ["string"],
      "keywords": ["string"]
    }}
  ]
}}

Rules:
- Output language: {language}
- Editorial niche: {niche}
- Suggest exactly {suggestion_count} timely card-news topics
- Each topic must be specific, practical, and non-clickbait
- Prefer ideas that can become educational, public-info, parenting, lifestyle, policy, or stats cards when relevant
- why_now must be one short sentence
- source_mix must use only the source ids present in the input
- keywords must be 1-4 short terms grounded in the signals
- Do not invent sources or claims that do not appear in the signals

Signals:
{json.dumps(compact_signals, ensure_ascii=False)}
""".strip()

    try:
        payload = generate_json(prompt)
    except Exception as exc:
        warning(f"Topic suggestion synthesis fell back to heuristics: {exc}", False)
        return _build_fallback_suggestions(signals, niche, language, suggestion_count)

    raw_topics = payload.get("topics", []) if isinstance(payload, dict) else []
    normalized_topics = []
    for item in raw_topics[:suggestion_count]:
        topic = _normalize_text(item.get("topic"))
        if not topic:
            continue

        why_now = _normalize_text(item.get("why_now"))
        source_mix = []
        if isinstance(item.get("source_mix"), list):
            for source in item["source_mix"]:
                normalized_source = _normalize_text(source).lower()
                if normalized_source and normalized_source not in source_mix:
                    source_mix.append(normalized_source)

        keywords = []
        if isinstance(item.get("keywords"), list):
            for keyword in item["keywords"]:
                normalized_keyword = _normalize_text(keyword)
                if normalized_keyword and normalized_keyword not in keywords:
                    keywords.append(normalized_keyword)

        normalized_topics.append(
            {
                "topic": topic[:72],
                "why_now": why_now[:180],
                "source_mix": source_mix,
                "keywords": keywords[:4],
            }
        )

    if len(normalized_topics) < suggestion_count:
        for fallback in _build_fallback_suggestions(
            signals,
            niche,
            language,
            suggestion_count,
        ):
            if any(
                existing["topic"].lower() == fallback["topic"].lower()
                for existing in normalized_topics
            ):
                continue
            normalized_topics.append(fallback)
            if len(normalized_topics) == suggestion_count:
                break

    if normalized_topics:
        return normalized_topics

    return _build_fallback_suggestions(signals, niche, language, suggestion_count)


def collect_topic_signals_for_profile(
    profile: dict,
    *,
    force_refresh: bool = False,
) -> dict:
    """
    Collects topic signals across configured sources and synthesizes topic ideas.

    Args:
        profile (dict): CardNews profile payload
        force_refresh (bool): Ignore cached report TTL

    Returns:
        report (dict): Topic signal report payload
    """
    config = get_topic_signal_config()
    profile_id = _normalize_text(profile.get("id"))
    niche = _normalize_text(profile.get("niche"))
    language = _normalize_text(profile.get("language")) or "English"
    cached = get_topic_signal_report(profile_id) if profile_id else None

    if cached and not force_refresh:
        cached_at = _isoformat_from_value(cached.get("updated_at"))
        if cached_at:
            try:
                parsed = datetime.fromisoformat(cached_at.replace("Z", "+00:00"))
                if _utc_now() - parsed <= timedelta(minutes=int(config["ttl_minutes"])):
                    return cached
            except ValueError:
                pass

    query_terms = _extract_query_terms(niche, extra_terms=profile.get("topic_terms", []))
    limit = int(config["max_items_per_source"])

    if niche:
        info(f"Collecting topic signals for niche: {niche}")

    signals = []
    errors = []
    collectors = [
        ("google_trends", lambda: _collect_google_trends(config, limit)),
        ("youtube", lambda: _collect_youtube(config, limit)),
        ("rss", lambda: _collect_rss(config, query_terms, limit)),
        ("reddit", lambda: _collect_reddit(config, query_terms, limit)),
        ("x", lambda: _collect_x(config, query_terms, limit)),
    ]

    for source_name, collector in collectors:
        try:
            signals.extend(collector())
        except Exception as exc:
            warning(f"Topic signal source '{source_name}' failed: {exc}", False)
            errors.append({"source": source_name, "error": str(exc)})

    deduped_signals = _dedupe_signals(signals)
    deduped_signals = sorted(deduped_signals, key=_signal_sort_key, reverse=True)
    keywords = _summarize_keywords(deduped_signals)
    suggestions = _build_topic_suggestions(
        deduped_signals,
        niche=niche,
        language=language,
        suggestion_count=int(config["suggestion_count"]),
    )

    report = {
        "profile_id": profile_id,
        "profile_nickname": _normalize_text(profile.get("nickname")),
        "niche": niche,
        "language": language,
        "region": config["region"],
        "query_terms": query_terms,
        "updated_at": _timestamp(),
        "source_summary": _build_source_summary(deduped_signals),
        "signals": deduped_signals[: max(20, limit * 3)],
        "keywords": keywords,
        "suggestions": suggestions,
        "errors": errors,
    }

    if profile_id:
        save_topic_signal_report(report)

    return report
