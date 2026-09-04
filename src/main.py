
import asyncio
import re
from urllib.parse import urljoin

from crawlee import Request
from crawlee.playwright_crawler import PlaywrightCrawler, PlaywrightCrawlingContext


START_URL = "https://www.ulta.com/brand/juvias-place"


def clean(value):
    if value is None:
        return None
    return re.sub(r"\s+", " ", value).strip()


def money(value):
    if not value:
        return None
    m = re.search(r"(\d+(?:\.\d{1,2})?)", value.replace(",", ""))
    return float(m.group(1)) if m else None


async def text_or_none(locator):
    try:
        if await locator.count():
            return clean(await locator.first.text_content())
    except Exception:
        pass
    return None


async def first_attr(locator, attr):
    try:
        if await locator.count():
            return await locator.first.get_attribute(attr)
    except Exception:
        pass
    return None


async def collect_product_urls(page):
    # Ulta renders product cards client-side. Scroll to trigger lazy loading.
    urls = set()
    stable_rounds = 0

    for _ in range(30):
        links = await page.locator('a[href*="/p/"]').evaluate_all(
            """els => els.map(a => a.href).filter(Boolean)"""
        )
        before = len(urls)
        urls.update(u.split("?")[0] for u in links if "/p/" in u)
        stable_rounds = stable_rounds + 1 if len(urls) == before else 0

        await page.evaluate("window.scrollBy(0, Math.max(700, window.innerHeight * 0.9))")
        await page.wait_for_timeout(900)

        if stable_rounds >= 4:
            break

    return sorted(urls)


async def product_links_from_page(page):
    urls = await collect_product_urls(page)
    return [
        Request.from_url(url, label="PRODUCT")
        for url in urls
    ]


async def scrape_product(context: PlaywrightCrawlingContext):
    page = context.page
    url = page.url

    await page.wait_for_load_state("domcontentloaded")
    await page.wait_for_timeout(1200)

    # JSON-LD is usually the most stable source for canonical product data.
    jsonld = await page.locator('script[type="application/ld+json"]').all_text_contents()

    product_json = None
    for raw in jsonld:
        try:
            import json
            data = json.loads(raw)
            candidates = data if isinstance(data, list) else [data]
            for item in candidates:
                if isinstance(item, dict) and item.get("@type") in ("Product", ["Product"]):
                    product_json = item
                    break
            if product_json:
                break
        except Exception:
            continue

    name = product_json.get("name") if product_json else None
    brand = None
    if product_json and isinstance(product_json.get("brand"), dict):
        brand = product_json["brand"].get("name")

    image = None
    if product_json:
        image = product_json.get("image")
        if isinstance(image, list):
            image = image[0] if image else None

    offers = product_json.get("offers") if product_json else None
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    offers = offers or {}

    price = offers.get("price")
    currency = offers.get("priceCurrency")

    if not name:
        name = await text_or_none(page.locator("h1"))

    if not brand:
        brand = await text_or_none(page.locator("a[href*='/brand/']").first)

    # Try common visible selectors as fallbacks.
    if price is None:
        price_text = await text_or_none(
            page.locator("text=/\\$\\s*\\d+(?:\\.\\d{1,2})?/").first
        )
        price = money(price_text)

    description = None
    if product_json:
        description = clean(product_json.get("description"))

    sku = product_json.get("sku") if product_json else None
    mpn = product_json.get("mpn") if product_json else None

    rating = None
    review_count = None
    aggregate = product_json.get("aggregateRating") if product_json else None
    if isinstance(aggregate, dict):
        rating = aggregate.get("ratingValue")
        review_count = aggregate.get("reviewCount")

    canonical = await first_attr(page.locator('link[rel="canonical"]'), "href")
    canonical = canonical or url

    data = {
        "url": canonical,
        "brand": brand,
        "name": clean(name),
        "sku": sku,
        "mpn": mpn,
        "description": description,
        "price": float(price) if str(price).replace(".", "", 1).isdigit() else price,
        "currency": currency or "USD",
        "rating": rating,
        "review_count": review_count,
        "image": image,
    }

    await context.push_data(data)


async def scrape_brand(context: PlaywrightCrawlingContext):
    page = context.page
    await page.wait_for_load_state("domcontentloaded")
    await page.wait_for_timeout(1500)

    requests = await product_links_from_page(page)

    max_products = context.request.user_data.get("max_products")
    if max_products:
        requests = requests[: int(max_products)]

    if not requests:
        # Fail loudly so a selector/site change is visible in the Actor run.
        raise RuntimeError("No Ulta product URLs were found on the brand page.")

    await context.add_requests(requests)


async def main():
    # Actor input is intentionally read from environment so this also works
    # in local Docker runs without requiring a specific Apify SDK version.
    import os
    import json

    input_data = {}
    raw = os.getenv("APIFY_INPUT")
    if raw:
        try:
            input_data = json.loads(raw)
        except json.JSONDecodeError:
            pass

    start_url = input_data.get("startUrl", START_URL)
    max_products = input_data.get("maxProducts")

    crawler = PlaywrightCrawler(
        max_requests_per_crawl=(int(max_products) + 5) if max_products else 250,
        headless=True,
    )

    @crawler.router.default_handler
    async def default_handler(context: PlaywrightCrawlingContext):
        if context.request.label == "PRODUCT":
            await scrape_product(context)
        else:
            await scrape_brand(context)

    request = Request.from_url(
        start_url,
        label="BRAND",
        user_data={"max_products": max_products},
    )

    await crawler.run([request])


if __name__ == "__main__":
    asyncio.run(main())
