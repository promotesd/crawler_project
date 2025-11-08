# src/parse.py
import re, json
from bs4 import BeautifulSoup
from typing import Dict, Any, List, Optional
from urllib.parse import urljoin, urlparse

# —— 归一化配置 ——
CURRENCY_SYMBOL_MAP = {"$":"USD","€":"EUR","£":"GBP","¥":"CNY"}

# 站点菜单里常见的“标准类目名”与关键词映射（可按需增减）
CATEGORY_CANON = {
    "jackets":      ["jacket", "jackets", "snowboard jackets", "ski jackets", "outerwear"],
    "pants":        ["pant", "pants", "snowboard pants", "ski pants", "bib", "bibs"],
    "leggings":     ["legging", "leggings"],
    "goggles":      ["goggle", "goggles"],
    "fleece":       ["fleece"],
    "base-layers":  ["base layer", "base layers", "baselayer", "baselayers"],
    "hoodies":      ["hoodie", "hoodies"],
    "t-shirts":     ["t-shirt", "t shirts", "tee", "tees"],
    "beanies":      ["beanie", "beanies"],
    "gloves":       ["glove", "gloves", "snowboard gloves"],
    "helmets":      ["helmet", "helmets", "ski helmets"],
    "facemasks":    ["facemask", "facemasks", "balaclava", "mask"],
    "ski-socks":    ["ski sock", "ski socks", "socks"],
    "backpacks":    ["backpack", "backpacks", "bag", "bags"],
    # 集合页信号（不用于产品最终类别，但可作为“这是列表页”的判断依据）
    "bestsellers":  ["bestseller", "best sellers", "bestsellers"],
    "new-arrivals": ["new in", "new-in", "new arrivals", "new-arrivals"],
    "sale":         ["sale", "discount"],
}

def parse_menu(html:str, base_url:str)->List[Dict[str, str]]:
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

def soupify(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")

def textnorm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()

def normalize_price_and_currency(price_raw):
    if price_raw is None: return None, ""
    if isinstance(price_raw, (int,float)): return float(price_raw), ""
    s = str(price_raw).strip()
    cur = ""
    for sym, code in CURRENCY_SYMBOL_MAP.items():
        if sym in s: cur = code; break
    s_num = re.sub(r"[^0-9.,]", "", s).replace(",", "")
    try: price = float(s_num) if s_num else None
    except ValueError: price = None
    return price, cur

def absolutize_images(images, base_url):
    out = []
    for src in images or []:
        if not src: continue
        if src.startswith("//"): out.append("https:" + src)
        elif src.startswith("/"): out.append(urljoin(base_url, src))
        else: out.append(src)
    seen=set(); dedup=[]
    for x in out:
        if x not in seen:
            seen.add(x); dedup.append(x)
    return dedup

# —— JSON-LD 工具 ——
def parse_json_ld_products(soup: BeautifulSoup) -> Optional[Dict[str, Any]]:
    for script in soup.select('script[type="application/ld+json"]'):
        try: obj = json.loads(script.string or "")
        except Exception: continue
        arr = obj if isinstance(obj, list) else [obj]
        for c in arr:
            t = c.get("@type") or c.get("@graph", [{}])[0].get("@type")
            types = [x.lower() for x in (t if isinstance(t, list) else [t] if t else [])]
            if any(x == "product" for x in types):
                return c
    return None

def has_jsonld_product(soup: BeautifulSoup) -> bool:
    return parse_json_ld_products(soup) is not None

def parse_json_ld_breadcrumbs(soup: BeautifulSoup) -> List[str]:
    cats = []
    for script in soup.select('script[type="application/ld+json"]'):
        try: obj = json.loads(script.string or "")
        except Exception: continue
        arr = obj if isinstance(obj, list) else [obj]
        for item in arr:
            if (item.get("@type") == "BreadcrumbList") or any(
                x.get("@type")=="BreadcrumbList" for x in item.get("@graph", [])
                if isinstance(item, dict) and isinstance(item.get("@graph"), list)
            ):
                elems = item.get("itemListElement") or []
                if isinstance(elems, list):
                    for e in elems:
                        name = e.get("name") or (e.get("item", {}) or {}).get("name")
                        if name: cats.append(textnorm(name))
    cats = [c for c in cats if c and c.lower() not in ("home","shop")]
    seen=set(); out=[]
    for c in cats:
        if c not in seen:
            seen.add(c); out.append(c)
    return out

def _first_text(soup, selectors: List[str]) -> str:
    for sel in selectors:
        node = soup.select_one(sel)
        if node: return textnorm(node.get_text(" ", strip=True))
    return ""

# —— 性别/类别识别 ——
def infer_categories_from_url_or_text(url: str, extra_text: str = "") -> List[str]:
    ctx = (url + " " + (extra_text or "")).lower()
    hits = []
    for canon, keys in CATEGORY_CANON.items():
        # 只把真正“品类”的映射加入（排除 best/new/sale 这些集合信号）
        if canon in {"bestsellers","new-arrivals","sale"}:
            continue
        for k in keys:
            if k in ctx:
                hits.append(canon); break
    seen=set(); out=[]
    for c in hits:
        if c not in seen:
            seen.add(c); out.append(c)
    return out

def detect_gender_from_url_or_text(url: str, extra_text: str = "") -> Optional[str]:
    ctx = f" {url} {(extra_text or '')} ".lower()
    if " women " in ctx or "/womens" in ctx or "womens-" in ctx: return "women"
    if " men " in ctx or "/mens" in ctx or "mens-" in ctx: return "men"
    return None

def get_canonical_url(soup: BeautifulSoup, url: str) -> str:
    for sel in ['link[rel="canonical"]','meta[property="og:url"]']:
        tag = soup.select_one(sel)
        href = (tag.get("href") if tag and tag.has_attr("href") else None) or (tag.get("content") if tag and tag.has_attr("content") else None)
        if href: return href.strip()
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}{p.path}"

def looks_like_listing_url(url: str, title_h1: str) -> bool:
    u = url.lower()
    t = (title_h1 or "").lower()
    if "page=" in u: return True
    # URL 或标题/H1 出现 men/women + 类目关键词，认为是列表/类目页
    has_gender = ("men" in u or "women" in u or "men" in t or "women" in t)
    cat_hits = any(any(k in u or k in t for k in keys) for keys in CATEGORY_CANON.values())
    return has_gender and cat_hits

def classify_page_context(html: str, url: str) -> Dict[str, Any]:
    """返回页面上下文并标记是否为‘类目/列表页’。只有在 is_category=True 时才会给产品打来源标签。"""
    soup = soupify(html)
    title = _first_text(soup, ["title"])
    h1 = _first_text(soup, ["h1","h1.page-title"])
    gender = detect_gender_from_url_or_text(url, f"{title} {h1}")
    cats = infer_categories_from_url_or_text(url, f"{title} {h1}")
    is_product = has_jsonld_product(soup)
    is_category = (not is_product) and looks_like_listing_url(url, f"{title} {h1}")
    return {"gender": gender, "categories": cats, "title": title, "h1": h1,
            "is_product": is_product, "is_category": is_category}

def is_listing_page_heuristic(soup, url: str):
    u = url.lower()
    if "page=" in u or "bestsellers" in u or "sale" in u: return True
    h1 = soup.find("h1")
    if h1:
        t = (h1.get_text(" ", strip=True) or "").lower()
        if any(k in t for k in ["best seller","new in","men","women","collection","category"]):
            return True
    return False

# —— 产品详情解析（JSON-LD 优先 + 价格归一 + 类别兜底） ——
def parse_product_page(html: str, url: str) -> Dict[str, Any]:
    soup = soupify(html)
    out: Dict[str, Any] = {"url": url, "canonical_url": get_canonical_url(soup, url)}

    pjson = parse_json_ld_products(soup)
    if pjson:
        out["name"] = pjson.get("name", "")
        offers = pjson.get("offers", {})
        if isinstance(offers, list) and offers: offers = offers[0]
        price_raw = offers.get("price") if isinstance(offers, dict) else None
        price, cur_from_sym = normalize_price_and_currency(price_raw)
        currency = offers.get("priceCurrency", "") if isinstance(offers, dict) else ""
        if not currency and cur_from_sym: currency = cur_from_sym
        out["price"] = price; out["priceCurrency"] = currency
        out["sku"] = pjson.get("sku", "")
        brand = pjson.get("brand", {}); out["brand"] = (brand.get("name","") if isinstance(brand, dict) else brand) or ""
        images = pjson.get("image", []); images = [images] if isinstance(images, str) else images
        out["images"] = absolutize_images(images, url)
        out["description"] = pjson.get("description", "")

    if not out.get("name"):
        out["name"] = _first_text(soup, ["h1","[data-testid='product-title']"])

    if out.get("price") is None:
        m = re.search(r"([$€£¥])?\s*\d[\d.,]*", soup.get_text(" ", strip=True))
        if m:
            p, cur = normalize_price_and_currency(m.group(0))
            out["price"] = p
            if not out.get("priceCurrency") and cur: out["priceCurrency"] = cur

    if not out.get("description"):
        out["description"] = _first_text(soup, [".product-description","[itemprop='description']", "section.description",".description"])

    if not out.get("images"):
        imgs = [img.get("src") for img in soup.select("img[src]")]
        imgs = [s for s in imgs if s and any(ext in s.lower() for ext in (".jpg",".jpeg",".png",".webp"))]
        out["images"] = absolutize_images(imgs[:10], url)

    # 详情页自己的类目（面包屑/URL 兜底）
    cats = parse_json_ld_breadcrumbs(soup)
    if not cats:
        title = _first_text(soup, ["title"])
        h1 = _first_text(soup, ["h1"])
        cats = infer_categories_from_url_or_text(url, f"{title} {h1}")
    out["categories"] = cats

    # 若像列表页但无 Product JSON-LD，则丢弃（防止把列表页当产品）
    if is_listing_page_heuristic(soup, url) and not pjson:
        return {}
    return out

# —— 只抽取“像详情页”的链接（/slug 形式；过滤集合页关键词与 query） ——
def discover_product_links_from_html(html: str, base_url: str) -> List[str]:
    soup = soupify(html)
    links = []
    for a in soup.select("a[href]"):
        href = a.get("href",""); 
        if not href or href.startswith("#"): continue
        h = href.lower()
        if any(x in h for x in ["account","cart","search","help","login","bestsellers","new-in","sale","page=","/blog","/travel"]):
            continue
        if "?" in h or "#" in h: continue
        path = h.split("?")[0]
        if path.count("/") != 1: continue   # 仅 /slug
        if "-" not in path: continue
        links.append(href)
    seen=set(); out=[]
    for h in links:
        if h not in seen:
            seen.add(h); out.append(h)
    return out
