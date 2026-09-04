# Ulta Juvia's Place Apify Actor

This Actor starts from:

https://www.ulta.com/brand/juvias-place

It scrolls the brand page to discover product links, then opens each product page and extracts product-level data.

## Output

Each dataset item contains:

- `url`
- `brand`
- `name`
- `sku`
- `mpn`
- `description`
- `price`
- `currency`
- `rating`
- `review_count`
- `image`

The Actor uses JSON-LD first and visible-page fallbacks where possible, making it less dependent on brittle CSS selectors.

## Run locally

Install Docker, then build:

```bash
docker build -t ulta-juvias-place .
```

For an Apify deployment, create an Actor from this source directory and build it.

## Notes

Ulta is a JavaScript-rendered ecommerce site. The crawler therefore uses Playwright rather than requests/BeautifulSoup.

The brand page currently exposes a large product catalog, so the Actor discovers product URLs before visiting individual product pages.
