import re, json
from bs4 import BeautifulSoup
from typing import Dict, Any, List, Optional
from urllib.parse import urljoin, urlparse



# --- 在文件顶部附近新增 ---
import re
from urllib.parse import urljoin

CURRENCY_SYMBOL_MAP = {
    "$": "USD", "€": "EUR", "£": "GBP", "¥": "CNY"
}

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
    # 去重
    seen=set(); dedup=[]
    for x in out:
        if x not in seen:
            seen.add(x); dedup.append(x)
    return dedup

def is_listing_page_heuristic(soup, url: str):
    u = url.lower()
    if "page=" in u or "bestsellers" in u or "sale" in u:
        return True
    h1 = soup.find("h1")
    if h1:
        t = (h1.get_text(" ", strip=True) or "").lower()
        if any(k in t for k in ["best seller","new in","men","women","collection","category"]):
            return True
    return False


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



def _first_text(soup, selectors: List[str]) -> str:
    for sel in selectors:
        node = soup.select_one(sel)
        if node:
            return textnorm(node.get_text(" ", strip=True))
    return ""

def parse_json_ld_products(soup: BeautifulSoup) -> Optional[Dict[str, Any]]:
    for script in soup.select('script[type="application/ld+json"]'):
        try: obj = json.loads(script.string or "")
        except Exception: continue
        candidates = obj if isinstance(obj, list) else [obj]
        for c in candidates:
            t = c.get("@type") or c.get("@graph", [{}])[0].get("@type")
            types = [x.lower() for x in (t if isinstance(t, list) else [t] if t else [])]
            if any(x=="product" for x in types):
                return c
    return None


def parse_json_ld_breadcrumbs(soup: BeautifulSoup) -> List[str]:
    """优先从 JSON-LD BreadcrumbList 取分类路径"""
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
                # itemListElement 里有位置与名称
                elems = item.get("itemListElement") or []
                if isinstance(elems, list):
                    for e in elems:
                        name = e.get("name") or (e.get("item", {}) or {}).get("name")
                        if name: cats.append(textnorm(name))
    # 去重/清洗
    cats = [c for c in cats if c and c.lower() not in ("home","shop")]
    seen=set(); out=[]
    for c in cats:
        if c not in seen:
            seen.add(c); out.append(c)
    return out


def get_canonical_url(soup: BeautifulSoup, url: str) -> str:
    for sel in ['link[rel="canonical"]','meta[property="og:url"]']:
        tag = soup.select_one(sel)
        href = (tag.get("href") if tag and tag.has_attr("href") else None) or (tag.get("content") if tag and tag.has_attr("content") else None)
        if href: return href.strip()
    # JSON-LD Product 里的 url
    pjson = parse_json_ld_products(soup)
    if pjson:
        u = pjson.get("url")
        if u: return u
    # 规范化：去 query/fragment
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

def infer_categories_from_url(url: str) -> List[str]:
    """URL 启发式（最后兜底）"""
    path = urlparse(url).path.strip("/")
    toks = [t for t in re.split(r"[/\-]", path) if t]
    # 只挑常见词
    keep = {"men","women","jacket","jackets","pant","pants","snowboard","ski","outerwear","bestsellers","sale","new"}
    return [t for t in toks if t.lower() in keep]

def parse_html_breadcrumbs(soup: BeautifulSoup) -> List[str]:
    """HTML 面包屑/导航兜底"""
    cats=[]
    for sel in ["nav.breadcrumb","ol.breadcrumb","ul.breadcrumb","[aria-label='breadcrumb']","nav[aria-label*=breadcrumb]"]:
        node = soup.select_one(sel)
        if node:
            texts = [textnorm(x.get_text(" ", strip=True)) for x in node.select("a, li") if textnorm(x.get_text(" ", strip=True))]
            cats.extend(texts)
            break
    cats=[c for c in cats if c and c.lower() not in ("home","shop")]
    seen=set(); out=[]
    for c in cats:
        if c not in seen:
            seen.add(c); out.append(c)
    return out

def parse_product_page(html: str, url: str) -> Dict[str, Any]:
    soup = soupify(html)
    out: Dict[str, Any] = {"url": url}

    # canonical
    out["canonical_url"] = get_canonical_url(soup, url)

    # JSON-LD 优先
    pjson = parse_json_ld_products(soup)
    if pjson:
        out["name"] = pjson.get("name", "")
        offers = pjson.get("offers", {})
        if isinstance(offers, list) and offers:
            offers = offers[0]
        price_raw = offers.get("price") if isinstance(offers, dict) else None
        price, cur_from_sym = normalize_price_and_currency(price_raw)
        currency = offers.get("priceCurrency", "") if isinstance(offers, dict) else ""
        if not currency and cur_from_sym: currency = cur_from_sym
        out["price"] = price
        out["priceCurrency"] = currency
        out["sku"] = pjson.get("sku", "")
        brand = pjson.get("brand", {})
        out["brand"] = (brand.get("name", "") if isinstance(brand, dict) else brand) or ""
        images = pjson.get("image", [])
        if isinstance(images, str): images = [images]
        out["images"] = absolutize_images(images, url)
        out["description"] = pjson.get("description", "")

    # 回退
    if not out.get("name"):
        out["name"] = _first_text(soup, ["h1", "h1.product-title", "[data-testid='product-title']"])
    if out.get("price") is None:
        m = re.search(r"([$€£¥])?\s*\d[\d.,]*", soup.get_text(" ", strip=True))
        if m:
            p, cur = normalize_price_and_currency(m.group(0))
            out["price"] = p
            if not out.get("priceCurrency") and cur:
                out["priceCurrency"] = cur
    if not out.get("description"):
        out["description"] = _first_text(soup, [".product-description", "[itemprop='description']", "section.description", ".description"])
    if not out.get("images"):
        imgs = [img.get("src") for img in soup.select("img[src]")]
        imgs = [s for s in imgs if s and any(ext in s.lower() for ext in (".jpg",".jpeg",".png",".webp"))]
        out["images"] = absolutize_images(imgs[:10], url)

    # 分类：JSON-LD 面包屑 -> HTML 面包屑 -> URL 启发式
    cats = parse_json_ld_breadcrumbs(soup)
    if not cats:
        cats = parse_html_breadcrumbs(soup)
    if not cats:
        cats = infer_categories_from_url(url)
    out["category"] = cats

    # 列表页过滤（JSON-LD 无 Product 且像列表）
    if is_listing_page_heuristic(soup, url) and not pjson:
        return {}

    return out


def discover_product_links_from_html(html: str, base_url: str) -> List[str]:
    soup = soupify(html)
    links = []
    for a in soup.select("a[href]"):
        href = a.get("href","")
        if not href or href.startswith("#"): continue
        h = href.lower()
        if any(x in h for x in ["account","cart","search","help","login","bestsellers","new-in","sale","page=","/blog","/travel"]):
            continue
        if "?" in h or "#" in h: continue
        path = h.split("?")[0]
        if path.count("/") != 1: continue   # /slug
        if "-" not in path: continue
        links.append(href)
    seen=set(); out=[]
    for h in links:
        if h not in seen:
            seen.add(h); out.append(h)
    return out