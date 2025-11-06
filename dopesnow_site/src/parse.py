import re, json
from bs4 import BeautifulSoup
from typing import Dict, Any, List, Optional

def soupify(html:str)->BeautifulSoup:
    return BeautifulSoup(html,"lxml")

def textnorm(s:str)->str:
    return re.sub(r"\s+", " ", s or "").strip()

def extract_build_id(html:str) -> Optional[str]:
    m=re.search(r"build[_ ]?id[\"\':\s]*([a-zA-Z0-9._-]+)", html, flags=re.I)
    if m:
        return m.group(1)
    m2 = re.search(r'"buildId"\s*:\s*"([^"]+)"', html)
    return m2.group(1) if m2 else None

def parse_menu(html:str, base_url:str)->List[Dict:str]:
    soup=soupify(html)
    items=[]
    navs=[]
    for sel in ["header", "footer", "nav"]:
        navs.extend(soup.select(sel+" a[herf]"))
    seen=set()
    for a in navs:
        href = a.get("href", "").strip()
        txt = textnorm(a.get_text(" ", strip=True))
        if not href or len(txt) < 1 or href.startswith("#"):
            continue
        key = (txt, href)
        if key in seen:
            continue
        seen.add(key)
        items.append({"text": txt, "href": href})
    return items



def _first_text(soup, selectors: List[str]) -> str:
    for sel in selectors:
        node = soup.select_one(sel)
        if node:
            return textnorm(node.get_text(" ", strip=True))
    return ""

def parse_json_ld_products(soup: BeautifulSoup) -> Optional[Dict[str, Any]]:
    data = {}
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            obj = json.loads(script.string or "")
        except Exception:
            continue
        candidates = obj if isinstance(obj, list) else [obj]
        for c in candidates:
            t = c.get("@type") or c.get("@graph", [{}])[0].get("@type")
            if isinstance(t, list):
                types = [x.lower() for x in t]
            else:
                types = [str(t).lower()] if t else []
            if any("product" == x for x in types):
                return c
    return None

def parse_product_page(html: str, url: str) -> Dict[str, Any]:
    soup = soupify(html)
    out: Dict[str, Any] = {"url": url}
    pjson = parse_json_ld_products(soup)
    if pjson:
        out["name"] = pjson.get("name", "")
        offers = pjson.get("offers", {})
        if isinstance(offers, list) and offers:
            offers = offers[0]
        out["price"] = offers.get("price") if isinstance(offers, dict) else ""
        out["priceCurrency"] = offers.get("priceCurrency") if isinstance(offers, dict) else ""
        out["sku"] = pjson.get("sku", "")
        brand = pjson.get("brand", {})
        out["brand"] = (brand.get("name", "") if isinstance(brand, dict) else brand) or ""
        images = pjson.get("image", [])
        if isinstance(images, str): images = [images]
        out["images"] = images
        out["description"] = pjson.get("description", "")
    if not out.get("name"):
        out["name"] = _first_text(soup, ["h1", "h1.product-title", "[data-testid='product-title']"])
    if not out.get("price"):
        m = re.search(r"\$\s?\d[\d.,]*", soup.get_text(" ", strip=True))
        out["price"] = m.group(0) if m else ""
    if not out.get("description"):
        out["description"] = _first_text(soup, [".product-description", "[itemprop='description']", "section.description", ".description"])
    if not out.get("images"):
        imgs = []
        for img in soup.select("img[src]"):
            src = img.get("src")
            if src and any(ext in src.lower() for ext in (".jpg", ".jpeg", ".png", ".webp")):
                imgs.append(src)
        seen = set(); dedup = []
        for x in imgs:
            if x not in seen:
                seen.add(x); dedup.append(x)
        out["images"] = dedup[:10]
    return out

def discover_product_links_from_html(html: str, base_url: str) -> List[str]:
    soup = soupify(html)
    links = []
    for a in soup.select("a[href]"):
        href = a.get("href","")
        if not href or href.startswith("#"):
            continue
        if href.count("/") <= 2 and len(href) > 1 and all(x not in href for x in ["account","cart","search","help","login"]):
            links.append(href)
    seen = set(); out = []
    for h in links:
        if h not in seen:
            seen.add(h); out.append(h)
    return out