import argparse
import json
import os
import requests
import warnings
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
import sys
import time
import re
import concurrent.futures
from collections import Counter
from datetime import datetime, timedelta
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlparse, urlunparse

# Headers for scraping to avoid basic bot detection
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

SOURCE_WEIGHTS = {
    "Hacker News": 1.2,
    "GitHub Trending": 1.2,
    "Product Hunt": 1.0,
    "36Kr": 1.0,
    "Tencent News": 0.9,
    "Wall Street CN": 0.9,
    "V2EX": 1.0,
    "Weibo Hot Search": 0.8,
}

AI_TERMS = {
    "ai", "llm", "gpt", "claude", "gemini", "deepseek", "rag", "agent",
    "machine learning", "ml", "model", "openai", "anthropic", "copilot", "transformer"
}

RSS_PLUS_FEEDS = [
    ("Simon Willison", "https://simonwillison.net/atom/everything/"),
    ("The Pragmatic Engineer", "https://newsletter.pragmaticengineer.com/feed"),
    ("Latent Space", "https://www.latent.space/feed"),
    ("OpenAI Blog", "https://openai.com/blog/rss.xml"),
    ("Google AI Blog", "https://blog.google/technology/ai/rss/"),
    ("The Batch", "https://www.deeplearning.ai/the-batch/feed/"),
    ("Hugging Face Blog", "https://huggingface.co/blog/feed.xml"),
    ("Anthropic News", "https://www.anthropic.com/news/rss.xml"),
    ("InfoQ AI", "https://www.infoq.com/ai-ml-data-eng/feed/"),
    ("MIT News AI", "https://news.mit.edu/rss/topic/artificial-intelligence2"),
]

NEWSNOW_API_URL = "https://newsnow.busiyi.world/api/s"
NEWSNOW_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
    "Cache-Control": "no-cache",
}
NEWSNOW_PLATFORMS = [
    ("toutiao", "今日头条"),
    ("baidu", "百度热搜"),
    ("wallstreetcn-hot", "华尔街见闻"),
    ("thepaper", "澎湃新闻"),
    ("bilibili-hot-search", "bilibili 热搜"),
    ("cls-hot", "财联社热门"),
    ("ifeng", "凤凰网"),
    ("tieba", "贴吧"),
    ("weibo", "微博"),
    ("douyin", "抖音"),
    ("zhihu", "知乎"),
]

def filter_items(items, keyword=None):
    if not keyword:
        return items
    keywords = [k.strip().lower() for k in keyword.split(',') if k.strip()]
    filtered = []
    for item in items:
        title = str(item.get("title", "")).lower()
        if any(k in title for k in keywords):
            filtered.append(item)
    return filtered

def fetch_url_content(url):
    """
    Fetches the content of a URL and extracts text from paragraphs.
    Truncates to 3000 characters.
    """
    if not url or not url.startswith('http'):
        return ""
    try:
        response = requests.get(url, headers=HEADERS, timeout=5)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
         # Remove script and style elements
        for script in soup(["script", "style", "nav", "footer", "header"]):
            script.extract()
        # Get text
        text = soup.get_text(separator=' ', strip=True)
        # Simple cleanup
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = ' '.join(chunk for chunk in chunks if chunk)
        return text[:3000]
    except Exception:
        return ""

def enrich_items_with_content(items, max_workers=10):
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_item = {executor.submit(fetch_url_content, item['url']): item for item in items}
        for future in concurrent.futures.as_completed(future_to_item):
            item = future_to_item[future]
            try:
                content = future.result()
                if content:
                    item['content'] = content
            except Exception:
                item['content'] = ""
    return items

def canonicalize_url(url):
    if not url or not str(url).startswith(("http://", "https://")):
        return ""
    try:
        parsed = urlparse(str(url).strip())
        netloc = parsed.netloc.lower().replace("www.", "")
        path = parsed.path.rstrip("/")
        blocked_query_keys = {"ref", "source", "from", "spm", "utm_source", "utm_medium", "utm_campaign"}
        query_pairs = []
        for key, value in parse_qsl(parsed.query, keep_blank_values=False):
            lowered = key.lower()
            if lowered.startswith("utm_") or lowered in blocked_query_keys:
                continue
            query_pairs.append((key, value))
        query = urlencode(sorted(query_pairs)) if query_pairs else ""
        return urlunparse((parsed.scheme.lower(), netloc, path, "", query, ""))
    except Exception:
        return str(url)

def normalize_title(title):
    text = unquote(str(title or "")).strip().lower()
    compact_ascii = re.sub(r"[^a-z0-9]+", "", text)
    if compact_ascii:
        return compact_ascii
    return re.sub(r"\s+", "", text)

def parse_heat_value(heat):
    text = str(heat or "").lower().replace(",", "").strip()
    if not text:
        return 0.0
    if "top product" in text:
        return 500.0
    match = re.search(r"(\d+(?:\.\d+)?)\s*([kmb万亿])?", text)
    if not match:
        return 0.0
    value = float(match.group(1))
    unit = match.group(2)
    if unit == "k":
        value *= 1000.0
    elif unit == "b":
        value *= 1000000000.0
    elif unit == "m":
        value *= 1000000.0
    elif unit == "万":
        value *= 10000.0
    elif unit == "亿":
        value *= 100000000.0
    return value

def parse_time_age_hours(time_str):
    text = str(time_str or "").strip().lower()
    if not text:
        return 48.0
    if text in {"today", "real-time", "realtime", "hot", "just now"}:
        return 1.0

    patterns = [
        (r"(\d+)\s*(minute|min|mins|minutes)\s*ago", 1.0 / 60.0),
        (r"(\d+)\s*(hour|hr|hrs|hours)\s*ago", 1.0),
        (r"(\d+)\s*(day|days)\s*ago", 24.0),
        (r"(\d+)\s*(week|weeks)\s*ago", 24.0 * 7.0),
        (r"(\d+)\s*分钟前", 1.0 / 60.0),
        (r"(\d+)\s*小时前", 1.0),
        (r"(\d+)\s*天前", 24.0),
    ]
    for pattern, multiplier in patterns:
        match = re.search(pattern, text)
        if match:
            return max(0.0, float(match.group(1)) * multiplier)

    now = datetime.now()
    time_formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%a, %d %b %Y %H:%M:%S %z",
    ]
    for fmt in time_formats:
        try:
            parsed = datetime.strptime(str(time_str).strip(), fmt)
            delta = now - parsed.replace(tzinfo=None)
            return max(0.0, delta.total_seconds() / 3600.0)
        except Exception:
            continue

    hhmm_match = re.match(r"^(\d{1,2}):(\d{2})$", text)
    if hhmm_match:
        hour = int(hhmm_match.group(1))
        minute = int(hhmm_match.group(2))
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate > now:
            candidate = candidate - timedelta(days=1)
        return max(0.0, (now - candidate).total_seconds() / 3600.0)

    return 48.0

def keyword_hit_count(title, keyword=None):
    if not keyword:
        return 0
    title_text = str(title or "").lower()
    keywords = [k.strip().lower() for k in str(keyword).split(",") if k.strip()]
    return sum(1 for k in keywords if k in title_text)

def source_weight(source):
    source_parts = [part.strip() for part in str(source or "").split("|") if part.strip()]
    if not source_parts:
        return 0.8
    weights = []
    for part in source_parts:
        if part in SOURCE_WEIGHTS:
            weights.append(SOURCE_WEIGHTS[part])
            continue
        if part.startswith("NewsNow "):
            weights.append(0.95)
            continue
        weights.append(0.8)
    return max(weights)

def infer_category(item):
    source = str(item.get("source", "")).lower()
    title = str(item.get("title", "")).lower()
    if "newsnow" in source:
        if any(token in source for token in ["微博", "财联社", "华尔街"]):
            return "Finance / Social"
        if any(token in source for token in ["知乎", "bilibili", "头条", "抖音", "百度"]):
            return "Global Headlines"
        if any(term in title for term in AI_TERMS):
            return "Tech & AI"
        return "Global Headlines"
    if "github trending" in source or "v2ex" in source:
        return "Open Source & Dev"
    if "wall street" in source or "weibo" in source:
        return "Finance / Social"
    if "rss+" in source or "hacker news" in source or "product hunt" in source:
        return "Tech & AI"
    if any(term in title for term in AI_TERMS):
        return "Tech & AI"
    return "Global Headlines"

def _item_quality(item):
    return (
        parse_heat_value(item.get("heat", ""))
        + (3.0 if item.get("time") else 0.0)
        + (2.0 if item.get("url") else 0.0)
    )

def merge_items(primary, secondary):
    merged = dict(primary)
    if _item_quality(secondary) > _item_quality(primary):
        merged = dict(secondary)
    src_a = str(primary.get("source", "")).strip()
    src_b = str(secondary.get("source", "")).strip()
    if src_a and src_b and src_a != src_b:
        src_set = []
        for src in (src_a.split("|") + src_b.split("|")):
            normalized = src.strip()
            if normalized and normalized not in src_set:
                src_set.append(normalized)
        merged["source"] = " | ".join(src_set)
    return merged

def dedupe_items(items):
    unique_items = []
    index_by_url = {}
    index_by_title = {}

    for raw_item in items:
        item = dict(raw_item)
        canonical_url = canonicalize_url(item.get("url", ""))
        normalized_title = normalize_title(item.get("title", ""))

        if canonical_url:
            item["url"] = canonical_url

        existing_index = None
        if canonical_url and canonical_url in index_by_url:
            existing_index = index_by_url[canonical_url]
        elif normalized_title and normalized_title in index_by_title:
            existing_index = index_by_title[normalized_title]

        if existing_index is None:
            unique_items.append(item)
            new_index = len(unique_items) - 1
            if canonical_url:
                index_by_url[canonical_url] = new_index
            if normalized_title:
                index_by_title[normalized_title] = new_index
        else:
            unique_items[existing_index] = merge_items(unique_items[existing_index], item)

    return unique_items

def rank_items(items, keyword=None):
    ranked = []
    for raw_item in items:
        item = dict(raw_item)
        heat_score = min(25.0, (parse_heat_value(item.get("heat", "")) + 1.0) ** 0.5)
        age_hours = parse_time_age_hours(item.get("time", ""))
        freshness_score = max(0.0, 20.0 - min(age_hours, 96.0) * 0.4)
        source_score = source_weight(item.get("source", "")) * 10.0
        keyword_score = float(keyword_hit_count(item.get("title", ""), keyword) * 8)

        total_score = round(source_score + heat_score + freshness_score + keyword_score, 2)
        item["score"] = total_score
        item["category"] = infer_category(item)
        ranked.append(item)

    ranked.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    return ranked

def build_highlights(items, keyword=None):
    if not items:
        return []

    source_counter = Counter()
    for item in items:
        for source in str(item.get("source", "")).split("|"):
            normalized = source.strip()
            if normalized:
                source_counter[normalized] += 1

    top_source = source_counter.most_common(1)[0] if source_counter else ("Unknown", 0)
    top_story = items[0].get("title", "")
    avg_top5 = round(sum(i.get("score", 0.0) for i in items[:5]) / max(1, min(5, len(items))), 2)

    highlights = [
        f"{len(items)} ranked stories collected across {len(source_counter)} active sources.",
        f"Most active source: {top_source[0]} ({top_source[1]} stories).",
        f"Average score of top stories: {avg_top5}.",
        f"Top story now: {top_story}",
    ]
    if keyword:
        highlights.append(f"Requested topic focus: {keyword}")
    return highlights[:5]

def item_to_markdown_block(item, index):
    title = item.get("title", "Untitled")
    url = item.get("url", "")
    source = item.get("source", "")
    time_str = item.get("time", "")
    heat = item.get("heat", "")
    score = item.get("score", 0)

    if url:
        header = f"### {index}. [{title}]({url})"
    else:
        header = f"### {index}. {title}"

    metadata_parts = [f"Source: {source}", f"Time: {time_str}"]
    if heat:
        metadata_parts.append(f"Heat: {heat}")
    metadata_parts.append(f"Score: {score}")

    return header + "\n" + "- " + " | ".join(metadata_parts) + "\n"

def generate_markdown_report(items, keyword=None):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    highlights = build_highlights(items, keyword=keyword)

    lines = [
        f"# Daily News Digest ({now})",
        "",
        "## Highlights",
    ]
    for tip in highlights:
        lines.append(f"- {tip}")

    lines.extend(["", "## Global Headlines", ""])
    for idx, item in enumerate(items[:5], start=1):
        lines.append(item_to_markdown_block(item, idx))

    sections = ["Tech & AI", "Open Source & Dev", "Finance / Social"]
    for section in sections:
        section_items = [item for item in items if item.get("category") == section]
        if not section_items:
            continue
        lines.extend(["", f"## {section}", ""])
        for idx, item in enumerate(section_items[:10], start=1):
            lines.append(item_to_markdown_block(item, idx))

    return "\n".join(lines).strip() + "\n"

def default_report_path():
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    return os.path.join("reports", f"news_digest_{ts}.md")

def write_report_file(report_text, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(report_text)

# --- Source Fetchers ---

def fetch_hackernews(limit=5, keyword=None):
    base_url = "https://news.ycombinator.com"
    news_items = []
    page = 1
    max_pages = 5
    
    while len(news_items) < limit and page <= max_pages:
        url = f"{base_url}/news?p={page}"
        try:
            response = requests.get(url, headers=HEADERS, timeout=10)
            if response.status_code != 200: break
        except: break

        soup = BeautifulSoup(response.text, 'html.parser')
        rows = soup.select('.athing')
        if not rows: break
        
        page_items = []
        for row in rows:
            try:
                id_ = row.get('id')
                title_line = row.select_one('.titleline a')
                if not title_line: continue
                title = title_line.get_text()
                link = title_line.get('href')
                
                # Metadata
                score_span = soup.select_one(f'#score_{id_}')
                score = score_span.get_text() if score_span else "0 points"
                
                # Age/Time
                age_span = soup.select_one(f'.age a[href="item?id={id_}"]')
                time_str = age_span.get_text() if age_span else ""
                
                if link and link.startswith('item?id='): link = f"{base_url}/{link}"
                
                page_items.append({
                    "source": "Hacker News", 
                    "title": title, 
                    "url": link, 
                    "heat": score,
                    "time": time_str
                })
            except: continue
        
        news_items.extend(filter_items(page_items, keyword))
        if len(news_items) >= limit: break
        page += 1
        time.sleep(0.5)

    return news_items[:limit]

def fetch_weibo(limit=5, keyword=None):
    # Use the PC Ajax API which returns JSON directly and is less rate-limited than scraping s.weibo.com
    url = "https://weibo.com/ajax/side/hotSearch"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://weibo.com/"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        items = data.get('data', {}).get('realtime', [])
        
        all_items = []
        for item in items:
            # key 'note' is usually the title, sometimes 'word'
            title = item.get('note', '') or item.get('word', '')
            if not title: continue
            
            # 'num' is the heat value
            heat = item.get('num', 0)
            
            # Construct URL (usually search query)
            # Web UI uses: https://s.weibo.com/weibo?q=%23TITLE%23&Refer=top
            full_url = f"https://s.weibo.com/weibo?q={quote(title)}&Refer=top"
            
            all_items.append({
                "source": "Weibo Hot Search", 
                "title": title, 
                "url": full_url, 
                "heat": f"{heat}",
                "time": "Real-time"
            })
            
        return filter_items(all_items, keyword)[:limit]
    except Exception: 
        return []

def fetch_github(limit=5, keyword=None):
    try:
        response = requests.get("https://github.com/trending", headers=HEADERS, timeout=10)
    except: return []
    
    soup = BeautifulSoup(response.text, 'html.parser')
    items = []
    for article in soup.select('article.Box-row'):
        try:
            h2 = article.select_one('h2 a')
            if not h2: continue
            title = h2.get_text(strip=True).replace('\n', '').replace(' ', '')
            link = "https://github.com" + h2['href']
            
            desc = article.select_one('p')
            desc_text = desc.get_text(strip=True) if desc else ""
            
            # Stars (Heat)
            # usually the first 'Link--muted' with a SVG star
            stars_tag = article.select_one('a[href$="/stargazers"]')
            stars = stars_tag.get_text(strip=True) if stars_tag else ""
            
            items.append({
                "source": "GitHub Trending", 
                "title": f"{title} - {desc_text}", 
                "url": link,
                "heat": f"{stars} stars",
                "time": "Today"
            })
        except: continue
    return filter_items(items, keyword)[:limit]

def fetch_36kr(limit=5, keyword=None):
    try:
        response = requests.get("https://36kr.com/newsflashes", headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        items = []
        for item in soup.select('.newsflash-item'):
            title = item.select_one('.item-title').get_text(strip=True)
            href = item.select_one('.item-title')['href']
            time_tag = item.select_one('.time')
            time_str = time_tag.get_text(strip=True) if time_tag else ""
            
            items.append({
                "source": "36Kr", 
                "title": title, 
                "url": f"https://36kr.com{href}" if not href.startswith('http') else href,
                "time": time_str,
                "heat": ""
            })
        return filter_items(items, keyword)[:limit]
    except: return []

def fetch_v2ex(limit=5, keyword=None):
    try:
        # Hot topics json
        data = requests.get("https://www.v2ex.com/api/topics/hot.json", headers=HEADERS, timeout=10).json()
        items = []
        for t in data:
            # V2EX API fields: created, replies (heat)
            replies = t.get('replies', 0)
            created = t.get('created', 0)
            # convert epoch to readable if possible, simpler to just leave as is or basic format
            # Let's keep it simple
            items.append({
                "source": "V2EX", 
                "title": t['title'], 
                "url": t['url'],
                "heat": f"{replies} replies",
                "time": "Hot"
            })
        return filter_items(items, keyword)[:limit]
    except: return []

def fetch_tencent(limit=5, keyword=None):
    try:
        url = "https://i.news.qq.com/web_backend/v2/getTagInfo?tagId=aEWqxLtdgmQ%3D"
        data = requests.get(url, headers={"Referer": "https://news.qq.com/"}, timeout=10).json()
        items = []
        for news in data['data']['tabs'][0]['articleList']:
            items.append({
                "source": "Tencent News", 
                "title": news['title'], 
                "url": news.get('url') or news.get('link_info', {}).get('url'),
                "time": news.get('pub_time', '') or news.get('publish_time', '')
            })
        return filter_items(items, keyword)[:limit]
    except: return []

def fetch_wallstreetcn(limit=5, keyword=None):
    try:
        url = "https://api-one.wallstcn.com/apiv1/content/information-flow?channel=global-channel&accept=article&limit=30"
        data = requests.get(url, timeout=10).json()
        items = []
        for item in data['data']['items']:
            res = item.get('resource')
            if res and (res.get('title') or res.get('content_short')):
                 ts = res.get('display_time', 0)
                 time_str = datetime.fromtimestamp(ts).strftime('%H:%M') if ts else ""
                 items.append({
                     "source": "Wall Street CN", 
                     "title": res.get('title') or res.get('content_short'), 
                     "url": res.get('uri'),
                     "time": time_str
                 })
        return filter_items(items, keyword)[:limit]
    except: return []

def fetch_producthunt(limit=5, keyword=None):
    try:
        # Using RSS for speed and reliability without API key
        response = requests.get("https://www.producthunt.com/feed", headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.text, 'xml')
        if not soup.find('item'): soup = BeautifulSoup(response.text, 'html.parser')
        
        items = []
        for entry in soup.find_all(['item', 'entry']):
            title = entry.find('title').get_text(strip=True)
            link_tag = entry.find('link')
            url = link_tag.get('href') or link_tag.get_text(strip=True) if link_tag else ""
            
            pubBox = entry.find('pubDate') or entry.find('published')
            pub = pubBox.get_text(strip=True) if pubBox else ""
            
            items.append({
                "source": "Product Hunt", 
                "title": title, 
                "url": url,
                "time": pub,
                "heat": "Top Product" # RSS implies top rank
            })
        return filter_items(items, keyword)[:limit]
    except: return []

def fetch_rssplus(limit=5, keyword=None):
    items = []
    per_feed_cap = max(1, min(3, limit))

    for feed_name, feed_url in RSS_PLUS_FEEDS:
        if len(items) >= limit:
            break
        try:
            response = requests.get(feed_url, headers=HEADERS, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "xml")
            entries = soup.find_all(["item", "entry"])

            feed_items = []
            for entry in entries:
                if len(feed_items) >= per_feed_cap or (len(items) + len(feed_items)) >= limit:
                    break

                title_tag = entry.find("title")
                if not title_tag:
                    continue
                title = title_tag.get_text(strip=True)

                link = ""
                link_tag = entry.find("link")
                if link_tag:
                    link = link_tag.get("href") or link_tag.get_text(strip=True)
                if not link:
                    guid_tag = entry.find("guid")
                    link = guid_tag.get_text(strip=True) if guid_tag else ""

                time_tag = entry.find("pubDate") or entry.find("published") or entry.find("updated")
                time_str = time_tag.get_text(strip=True) if time_tag else ""

                feed_items.append({
                    "source": f"RSS+ {feed_name}",
                    "title": title,
                    "url": link,
                    "time": time_str,
                    "heat": "",
                })

            items.extend(filter_items(feed_items, keyword))
        except Exception:
            continue

    return items[:limit]

def fetch_newsnow_platform(platform_id, display_name, limit=5, keyword=None):
    try:
        response = requests.get(
            f"{NEWSNOW_API_URL}?id={platform_id}&latest",
            headers=NEWSNOW_HEADERS,
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
        entries = payload.get("items", [])

        updated_ms = payload.get("updatedTime")
        time_str = "Latest"
        if isinstance(updated_ms, (int, float)) and updated_ms > 0:
            try:
                time_str = datetime.fromtimestamp(float(updated_ms) / 1000.0).strftime("%Y-%m-%d %H:%M")
            except Exception:
                pass

        items = []
        for entry in entries:
            title = str(entry.get("title", "")).strip()
            if not title:
                continue
            url = entry.get("url") or entry.get("mobileUrl") or ""
            extra = entry.get("extra") if isinstance(entry.get("extra"), dict) else {}
            heat = extra.get("info", "") if extra else ""
            items.append(
                {
                    "source": f"NewsNow {display_name}",
                    "title": title,
                    "url": url,
                    "heat": heat,
                    "time": time_str,
                }
            )

        return filter_items(items, keyword)[:limit]
    except Exception:
        return []

def fetch_newsnow(limit=5, keyword=None):
    all_items = []
    for platform_id, display_name in NEWSNOW_PLATFORMS:
        platform_items = fetch_newsnow_platform(platform_id, display_name, limit=limit, keyword=keyword)
        all_items.extend(platform_items)
    return all_items

def main():
    parser = argparse.ArgumentParser()
    core_sources_map = {
        'hackernews': fetch_hackernews, 'weibo': fetch_weibo, 'github': fetch_github,
        '36kr': fetch_36kr, 'v2ex': fetch_v2ex, 'tencent': fetch_tencent,
        'wallstreetcn': fetch_wallstreetcn, 'producthunt': fetch_producthunt
    }
    newsnow_sources_map = {
        "newsnow": fetch_newsnow,
    }
    for platform_id, display_name in NEWSNOW_PLATFORMS:
        source_key = f"newsnow-{platform_id}"
        newsnow_sources_map[source_key] = (
            lambda pid=platform_id, name=display_name: (
                lambda limit=5, keyword=None: fetch_newsnow_platform(pid, name, limit=limit, keyword=keyword)
            )
        )()

    sources_map = dict(core_sources_map)
    sources_map['rssplus'] = fetch_rssplus
    sources_map.update(newsnow_sources_map)
    
    parser.add_argument('--source', default='all', help='Source(s) to fetch from (comma-separated)')
    parser.add_argument('--pack', choices=['core', 'plus', 'trend'], default='core', help='Source bundle for --source all')
    parser.add_argument('--limit', type=int, default=10, help='Limit per source. Default 10')
    parser.add_argument('--keyword', help='Comma-sep keyword filter')
    parser.add_argument('--top', type=int, default=0, help='Return top N ranked items (0 keeps all)')
    parser.add_argument('--deep', action='store_true', help='Download article content for detailed summarization')
    parser.add_argument('--deep-top', type=int, default=20, help='Top N ranked items to deep-fetch when --deep is used')
    parser.add_argument('--report', action='store_true', help='Write a structured markdown report to reports/')
    parser.add_argument('--report-file', help='Custom markdown report output path')
    
    args = parser.parse_args()
    
    to_run = []
    if args.source == 'all':
        to_run = list(core_sources_map.values())
        if args.pack == 'plus':
            to_run.append(fetch_rssplus)
        elif args.pack == 'trend':
            to_run.append(fetch_newsnow)
    else:
        requested_sources = [s.strip() for s in args.source.split(',')]
        for source_name in requested_sources:
            if source_name in sources_map:
                to_run.append(sources_map[source_name])
            
    results = []
    for func in to_run:
        try:
            results.extend(func(args.limit, args.keyword))
        except Exception:
            pass

    results = dedupe_items(results)
    results = rank_items(results, keyword=args.keyword)

    if args.top and args.top > 0:
        results = results[:args.top]
        
    if args.deep and results:
        deep_target_count = min(max(1, args.deep_top), len(results))
        sys.stderr.write(f"Deep fetching content for top {deep_target_count} ranked items (of {len(results)})...\n")
        enrich_items_with_content(results[:deep_target_count])

    if args.report and results:
        report_path = args.report_file or default_report_path()
        try:
            report_text = generate_markdown_report(results, keyword=args.keyword)
            write_report_file(report_text, report_path)
            sys.stderr.write(f"Report saved to {report_path}\n")
        except Exception as error:
            sys.stderr.write(f"Failed to write report: {error}\n")
        
    print(json.dumps(results, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
