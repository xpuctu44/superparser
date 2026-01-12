from __future__ import annotations

import re
import json
import httpx
from bs4 import BeautifulSoup


PRICE_REGEX = re.compile(r"(?:(?:\d+[\s\.,]?)+\d*)")
INSTALLMENT_KEYWORDS = (
    "/мес", " в мес", "мес ", "мес.", "ежемес", "ежемесяч", "каждый месяц", "в месяц",
    "в рассрочку", "рассроч", "кредит", "платеж", "платёж", "взнос", "помесяч"
)


from typing import Optional


async def fetch_price(url: str, *, css_selector: Optional[str] = None) -> Optional[float]:
    async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
        resp = await client.get(url, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36",
        })
        resp.raise_for_status()
        html = resp.text

    soup = BeautifulSoup(html, "lxml")
    # collect (text, source_priority, source_tag) where lower is better
    candidates: list[tuple[str, int, str]] = []
    is_apple_market = "apple-market.net" in url.lower()
    
    # Special handling for apple-market: prioritize js-product-price element
    if is_apple_market:
        price_el = soup.select_one("#js-product-price[itemprop='price'], #js-product-price[itemprop=price]")
        if price_el:
            txt = price_el.get("content") or price_el.get("value")
            if txt:
                candidates.append((txt, -1, "itemprop-content"))  # Highest priority
            else:
                txt = price_el.get_text(" ", strip=True)
                if txt:
                    candidates.append((txt, -1, "itemprop-text"))
    
    if css_selector:
        for el in soup.select(css_selector):
            txt = el.get_text(" ", strip=True)
            if txt:
                candidates.append((txt, 2, "css"))
    if not candidates:
        # 1) meta tags and elements with itemprop="price"
        for sel in ["meta[itemprop=price]", "meta[property='product:price:amount']", "[itemprop='price']", "[itemprop=price]"]:
            for el in soup.select(sel):
                # Prioritize content attribute over text content
                txt = el.get("content") or el.get("value") or el.get_text(" ", strip=True)
                if txt:
                    candidates.append((txt, 0, "meta"))
        # 2) JSON-LD structured data
        for script in soup.select("script[type='application/ld+json']"):
            try:
                data = json.loads(script.string or "{}")
            except Exception:
                continue
            # normalize to list
            blobs = data if isinstance(data, list) else [data]
            for blob in blobs:
                if not isinstance(blob, dict):
                    continue
                # Product with offers
                if (blob.get("@type") == "Product") or ("offers" in blob):
                    offers = blob.get("offers")
                    if isinstance(offers, list):
                        for offer in offers:
                            price = offer.get("price") if isinstance(offer, dict) else None
                            if price:
                                candidates.append((str(price), 1, "jsonld"))
                    elif isinstance(offers, dict):
                        price = offers.get("price")
                        if price:
                            candidates.append((str(price), 1, "jsonld"))
                # Direct price field
                price = blob.get("price")
                if price:
                    candidates.append((str(price), 1, "jsonld"))
        # 3) common price containers
        for sel in [".price", "[class*='price']", "[id*='price']"]:
            for el in soup.select(sel):
                txt = el.get("content") or el.get_text(" ", strip=True)
                if txt:
                    candidates.append((txt, 2, "generic"))

    # filter out installment/credit texts
    filtered: list[tuple[str, int, str]] = []
    is_apple_market = "apple-market.net" in url.lower()
    for (t, p, s) in candidates:
        tl = t.lower()
        if any(k in tl for k in INSTALLMENT_KEYWORDS):
            continue
        # For apple-market, require currency sign in free-text sources to avoid stray numbers (e.g., monthly payments)
        if is_apple_market and s in ("css", "generic"):
            if ("₽" not in t) and (" руб" not in tl) and ("руб." not in tl):
                continue
            # For apple-market, also check if the text contains very low prices that might be installments
            # Extract all numbers and if the max is too low (< 30000), skip it
            nums_in_text = []
            for match in PRICE_REGEX.finditer(t.replace("\xa0", " ")):
                num = match.group(0).replace(" ", "").replace("\u00a0", "").replace(",", ".")
                try:
                    value = float(num)
                    if value > 0:
                        nums_in_text.append(value)
                except ValueError:
                    continue
            if nums_in_text and max(nums_in_text) < 30000:
                # This text only contains very low prices, likely installments
                continue
        filtered.append((t, p, s))
    # sort by source priority to prefer meta/jsonld over generic blocks
    filtered.sort(key=lambda tp: tp[1])

    # take best-priority group only
    if not filtered:
        return None
    best_prio = filtered[0][1]
    best_group_full = [(t, s) for (t, p, s) in filtered if p == best_prio]
    # If within best group we have itemprop-content (from content attribute), prioritize it
    if any(s == "itemprop-content" for _, s in best_group_full):
        best_group = [t for (t, s) in best_group_full if s == "itemprop-content"]
    # If within best group we have JSON-LD, restrict to those
    elif any(s == "jsonld" for _, s in best_group_full):
        best_group = [t for (t, s) in best_group_full if s == "jsonld"]
    else:
        best_group = [t for (t, s) in best_group_full]

    # If URL hints capacity (e.g., 256gb/512gb/1tb), score candidates accordingly
    url_l = url.lower()
    desired_capacity = None
    if any(k in url_l for k in ("256gb", "256-гб", "256гб", "256-gb", "256 gb")):
        desired_capacity = "256"
    elif any(k in url_l for k in ("512gb", "512-гб", "512гб", "512-gb", "512 gb")):
        desired_capacity = "512"
    elif any(k in url_l for k in ("1tb", "1-тб", "1тб", "1-tb", "1 tb")):
        desired_capacity = "1tb"

    def capacity_score(text: str) -> int:
        t = text.lower()
        score = 0
        if "₽" in text or " руб" in t or "руб." in t:
            score += 1
        if desired_capacity:
            if desired_capacity == "256" and ("256" in t or "256gb" in t):
                score += 3
            if desired_capacity == "512" and ("512" in t or "512gb" in t):
                score += 3
            if desired_capacity == "1tb" and ("1tb" in t or "1 тб" in t or "1тб" in t):
                score += 3
            # penalize mismatching larger capacities when 256 is desired
            if desired_capacity == "256" and ("1tb" in t or "512" in t):
                score -= 2
        return score

    # Prefer candidate within best group with highest capacity score
    if best_group:
        best_group_sorted = sorted(best_group, key=lambda txt: capacity_score(txt), reverse=True)
        chosen_text = best_group_sorted[0]
    else:
        chosen_text = filtered[0][0]

    # Parse numbers from all texts of the chosen group and choose plausible value
    numeric_values: list[float] = []
    parse_group = best_group if best_group else [filtered[0][0]]
    for text in parse_group:
        # First, try direct parsing if text looks like a pure number (from content attribute)
        text_clean = text.strip().replace("\xa0", "").replace(" ", "").replace(",", ".")
        direct_value = None
        try:
            parsed = float(text_clean)
            if parsed > 0:
                numeric_values.append(parsed)
                direct_value = parsed
        except ValueError:
            pass
        # Also parse using regex for cases with formatting
        # (if direct parse succeeded and value is same, skip to avoid duplicates)
        for match in PRICE_REGEX.finditer(text.replace("\xa0", " ")):
            num = match.group(0)
            num_norm = num.replace(" ", "").replace("\u00a0", "").replace(",", ".")
            try:
                value = float(num_norm)
                if value > 0:
                    # Skip if we already have this value from direct parse
                    if direct_value is None or abs(value - direct_value) >= 0.01:
                        numeric_values.append(value)
            except ValueError:
                continue
    if not numeric_values:
        return None
    
    # Special handling for apple-market.net
    if is_apple_market:
        # For apple-market, filter out very low values that might be installment prices
        # and prefer higher values in the reasonable range
        plausible = [v for v in numeric_values if 50000 <= v <= 500000]
        if plausible:
            # If we have multiple plausible values, prefer the one closest to typical iPhone price range
            # For high-end iPhones, prices are usually 80k-150k, so prefer values in that range
            high_end = [v for v in plausible if 80000 <= v <= 150000]
            if high_end:
                # Return the maximum among high-end prices to avoid installment/old price
                return max(high_end)
            # Otherwise return the maximum plausible value
            return max(plausible)
        # Fallback: values >= 30000 (to exclude installment prices)
        high_values = [v for v in numeric_values if v >= 30000]
        if high_values:
            return max(high_values)
        return None
    
    # Default heuristic for other sites:
    # - Prefer values in [10000, 500000] range; pick the minimum to favor discounted/base price
    plausible = [v for v in numeric_values if 10000 <= v <= 500000]
    if plausible:
        return min(plausible)
    # fallback: any value >= 10000
    high_values = [v for v in numeric_values if v >= 10000]
    if high_values:
        return min(high_values)
    return None


def _extract_model_capacity_color(title: str) -> tuple[str, Optional[str], Optional[str]]:
    t = title.strip()
    tl = t.lower()
    # capacity detection
    cap = None
    for token in ["1tb", "2tb", "512gb", "256gb", "128gb", "64gb"]:
        if token in tl:
            cap = token.upper()
            break
    if not cap:
        for token in ["1 тб", "1тб", "512 гб", "512гб", "256 гб", "256гб", "128 гб", "128гб", "64 гб", "64гб"]:
            if token in tl:
                cap = token.upper().replace(" ", "")
                break
    # simple color detection
    colors = [
        ("black", ["black", "черн", "graphite", "титан черн"]),
        ("white", ["white", "бел", "starlight"]),
        ("blue", ["blue", "син", "голуб", "navy"]),
        ("green", ["green", "зел"]),
        ("pink", ["pink", "роз"]),
        ("titanium", ["titanium", "титан", "titan"]),
        ("desert", ["desert", "бронз", "desert titanium"]),
    ]
    color = None
    for cname, keys in colors:
        if any(k in tl for k in keys):
            color = cname
            break
    # model name: strip capacity/color markers from end
    model = t
    if cap and cap in model.upper():
        model = re.sub(r"(?i)\b(" + re.escape(cap) + r")\b", "", model)
    if color:
        model = re.sub(r"(?i)\b(" + color + r")\b", "", model)
    model = re.sub(r"\s+", " ", model).strip()
    return model, cap, color


async def discover_products(list_pages: list[str], *, link_selector: Optional[str] = None, title_selector: Optional[str] = None, client: Optional[httpx.AsyncClient] = None) -> list[dict]:
    close_client = False
    if client is None:
        client = httpx.AsyncClient(follow_redirects=True, timeout=30)
        close_client = True
    seen_urls: set[str] = set()
    results: list[dict] = []
    try:
        for page in list_pages:
            try:
                resp = await client.get(page, headers={
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36",
                })
                resp.raise_for_status()
            except Exception:
                continue
            soup = BeautifulSoup(resp.text, "lxml")
            # choose selectors: provided or sensible defaults
            selectors = [link_selector] if link_selector else [
                "a.product-item__link",
                "a.product-card",
                "a.product-card__link",
                ".product-card a[href]",
                ".catalog-item a[href]",
                ".product-item__title a",
                ".grid .item a[href]",
                "a[href*='/product/']",
                "a[href*='/products/']",
                # maxmobiles.ru specific
                "a[href*='/iphone/']",
                "a[href*='/ipad/']",
                "a[href*='/watch/']",
                "a[href*='/macbook/']",
                "a[href*='/airpods/']",
                # generic fallbacks
                "a[href]",
            ]
            found_links = []
            for sel in selectors:
                found_links = soup.select(sel)
                if found_links:
                    break
            for a in found_links:
                href = a.get("href")
                if not href:
                    continue
                if href.startswith("/") and page.startswith("http"):
                    from urllib.parse import urljoin
                    href = urljoin(page, href)
                if not href.startswith("http"):
                    continue
                # Filter out non-product links (filters/categories)
                from urllib.parse import urlparse
                parsed = urlparse(href)
                path = parsed.path or "/"
                path_lower = path.lower()
                query_lower = (parsed.query or "").lower()
                # Skip obvious filter/sort/pagination and anchors
                if any(k in path_lower for k in ["/filter", "/filters", "/brand", "/series"]) or \
                   any(k in query_lower for k in ["filter", "sort", "page=", "min", "max", "color=", "memory=", "gb=", "tb="]):
                    continue
                # Skip top-level categories
                category_names = {"iphone", "ipad", "watch", "mac", "macbook", "airpods", "accessories", "aksessuary", "gadgets", "dyson"}
                parts = [p for p in path.split("/") if p]
                if len(parts) <= 1 and (parts and parts[0].lower() in category_names):
                    continue
                # Heuristic: accept if explicit product path markers present
                is_product_marker = ("/product" in path_lower) or ("/products" in path_lower)
                # Or if last segment looks like a product slug (has hyphens and letters+digits)
                last = parts[-1] if parts else ""
                looks_like_slug = ("-" in last) and (re.search(r"[a-zа-я]", last, re.I) is not None)
                if not (is_product_marker or looks_like_slug):
                    continue
                # Deduplicate by normalized URL without query/fragment
                normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                if normalized in seen_urls:
                    continue
                seen_urls.add(normalized)
                title_text = a.get_text(" ", strip=True)
                if title_selector:
                    # try to refine: find closest title element inside link
                    inner = a.select_one(title_selector)
                    if inner:
                        title_text = inner.get_text(" ", strip=True) or title_text
                if not title_text:
                    continue
                model, capacity, color = _extract_model_capacity_color(title_text)
                results.append({
                    "url": href,
                    "title": title_text,
                    "model": model,
                    "capacity": capacity,
                    "color": color,
                })
        return results
    finally:
        if close_client:
            await client.aclose()

