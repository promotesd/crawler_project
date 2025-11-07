# src/products.py
from typing import List, Dict, Set
from urllib.parse import urljoin, urlparse
import xml.etree.ElementTree as ET
import requests
from tqdm import tqdm

from httpclient import HttpClient
from parse import discover_product_links_from_html, parse_product_page, soupify

CATEGORY_ALLOW = [
    "men","women","jacket","jackets","pant","pants",
    "outerwear","snow","ski","snowboard","best","sale","new"
]
CATEGORY_DENY = ["account","cart","login","help","search","blog","travel"]

def fetch_sitemap_urls(base_url: str, limit: int = 4000) -> List[str]:
    base = base_url.rstrip("/")
    candidates = [f"{base}/sitemap.xml"]
    def fetch_one(xml_url: str):
        try:
            r = requests.get(xml_url, timeout=20, headers={"User-Agent":"Mozilla/5.0"})
            r.raise_for_status()
        except Exception:
            return []
        try:
            root = ET.fromstring(r.text)
        except Exception:
            return []
        ns={"sm":"http://www.sitemaps.org/schemas/sitemap/0.9"}
        urls=[loc.text.strip() for loc in root.findall(".//sm:url/sm:loc", ns) if loc.text]
        if urls:
            return urls
        subs=[loc.text.strip() for loc in root.findall(".//sm:sitemap/sm:loc", ns) if loc.text]
        return subs
    visited_sm:set[str]=set()
    queue=list(candidates)
    all_urls:List[str]=[]
    while queue and len(all_urls)<limit:
        sm=queue.pop(0)
        if sm in visited_sm: continue
        visited_sm.add(sm)
        got=fetch_one(sm)
        if not got: continue
        if got and got[0].lower().endswith(".xml"):
            queue.extend([s for s in got if s not in visited_sm])
        else:
            all_urls.extend(got)
    host = urlparse(base_url).netloc.lower()
    wanted=[]
    for u in all_urls:
        if urlparse(u).netloc.lower()!=host: continue
        lu=u.lower()
        if any(k in lu for k in ["snow","jacket","pant","hoodie","men","women","product","outerwear"]):
            wanted.append(u)
    # 去重
    seen=set(); out=[]
    for u in wanted:
        if u not in seen:
            seen.add(u); out.append(u)
        if len(out)>=limit: break
    return out

def discover_category_links_from_html(html: str, base_url: str) -> List[str]:
    soup = soupify(html)
    links=[]
    for a in soup.select("a[href]"):
        href=a.get("href","")
        if not href or href.startswith("#"): continue
        if href.startswith("/"):
            href=urljoin(base_url, href)
        if urlparse(href).netloc.lower()!=urlparse(base_url).netloc.lower():
            continue
        h=href.lower()
        if any(x in h for x in CATEGORY_DENY): continue
        if any(k in h for k in CATEGORY_ALLOW) or ("?page=" in h):
            links.append(href)
    seen=set(); out=[]
    for h in links:
        if h not in seen:
            seen.add(h); out.append(h)
    return out

def normalize_url(u: str) -> str:
    """去掉 query/fragment，保留 scheme+host+path，便于去重"""
    p = urlparse(u)
    return f"{p.scheme}://{p.netloc}{p.path}"

def merge_product(dst: Dict, src: Dict):
    """合并两个同产品记录（以 canonical/SKU 判断为同一），聚合信息与分类"""
    # 优先保留已有字段，不覆盖有效值；把 categories 合并去重
    for k in ["name","price","priceCurrency","sku","brand","description","images"]:
        dv = dst.get(k)
        sv = src.get(k)
        if (dv in [None,"",[]]) and sv not in [None,"",[]]:
            dst[k] = sv
    cats = set(dst.get("categories",[]) or []) | set(src.get("categories",[]) or [])
    dst["categories"] = sorted(cats)

def crawl_products(client: HttpClient, seeds: List[str], max_pages: int = 200) -> List[Dict]:
    visited: Set[str] = set()
    product_urls: Set[str] = set()
    queue: List[str] = []

    # 初始种子
    if not seeds:
        seeds = [client.settings.base_url]
    if len(seeds) <= 1:
        sm_seeds = fetch_sitemap_urls(client.settings.base_url, limit=4000)
        if sm_seeds:
            print(f"  Loaded {len(sm_seeds)} seeds from sitemap.xml")
            seeds = list(set(seeds + sm_seeds))

    for s in seeds:
        if s.startswith("/"): s = urljoin(client.settings.base_url, s)
        queue.append(s)

    # 发现阶段
    pages = 0
    from tqdm import tqdm
    with tqdm(total=max_pages, desc="Discovering pages", unit="page") as pbar:
        while queue and pages < max_pages:
            url = queue.pop(0)
            if url in visited: continue
            try:
                resp = client.get(url)
            except Exception:
                pages += 1; pbar.update(1); continue
            visited.add(url); pages += 1; pbar.update(1)
            html = resp.text

            # 详情候选
            for href in discover_product_links_from_html(html, client.settings.base_url):
                absu = urljoin(client.settings.base_url, href) if href.startswith("/") else href
                product_urls.add(normalize_url(absu))

            # 类目/分页扩展
            for link in discover_category_links_from_html(html, client.settings.base_url)[:50]:
                if link not in visited:
                    queue.append(link)

    print(f"  Discovered product URL candidates: {len(product_urls)}")

    # 解析 + 去重合并
    products_by_key: Dict[str, Dict] = {}   # key 优先 canonical_url，其次 normalize_url
    for purl in tqdm(sorted(product_urls), desc="Parsing products", unit="product"):
        try:
            resp = client.get(purl)
            pdata = parse_product_page(resp.text, purl)
            if not (pdata.get("name") or (pdata.get("price") is not None)):
                continue
            # 选 key：canonical > normalized
            key = pdata.get("canonical_url") or normalize_url(purl)
            key = normalize_url(key)

            if key not in products_by_key:
                products_by_key[key] = pdata
            else:
                merge_product(products_by_key[key], pdata)

            # 若有 SKU，也可建立次级去重（避免颜色变体重复）
            sku = pdata.get("sku")
            if sku:
                sku_key = f"sku::{sku}"
                if sku_key not in products_by_key:
                    products_by_key[sku_key] = products_by_key[key]
                else:
                    merge_product(products_by_key[sku_key], products_by_key[key])

        except Exception:
            continue

    # 将真正的产品对象（非 sku:: 键）输出
    result = []
    seen_ids = set()
    for k, v in products_by_key.items():
        if k.startswith("sku::"):  # 跳过 SKU 索引键
            continue
        if id(v) in seen_ids:
            continue
        seen_ids.add(id(v))
        result.append(v)
    return result
