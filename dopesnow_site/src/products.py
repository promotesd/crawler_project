# src/products.py
from typing import List, Dict, Set
from urllib.parse import urljoin, urlparse
import xml.etree.ElementTree as ET
import requests
from tqdm import tqdm

from http import HttpClient
from parse import (
    discover_product_links_from_html,
    parse_product_page,
    soupify,
    classify_page_context,   # 现在包含 is_category / is_product 标记
)

CATEGORY_DENY = ["account","cart","login","help","search","blog","travel"]

def normalize_url(u: str) -> str:
    p = urlparse(u)
    return f"{p.scheme}://{p.netloc}{p.path}"

# sitemap 作为补种子（含列表页 & 详情页 URL）
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
        if urls: return urls
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
        if any(k in lu for k in [
            "men","women","snow","jacket","pant","hoodie","goggle","fleece","base","t-shirt",
            "beanie","glove","helmet","mask","sock","backpack","outerwear","facemask"
        ]):
            wanted.append(u)

    seen=set(); out=[]
    for u in wanted:
        if u not in seen:
            seen.add(u); out.append(u)
        if len(out)>=limit: break
    return out

def crawl_products(client: HttpClient, seeds: List[str], max_pages: int = 200) -> List[Dict]:
    visited: Set[str] = set()
    queue: List[str] = []
    product_urls: Set[str] = set()
    product_contexts: Dict[str, List[Dict]] = {}  # 仅记录来自“类目/列表页”的来源

    # 初始化 seeds
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

    # BFS
    pages = 0
    with tqdm(total=max_pages, desc="Discovering pages", unit="page") as pbar:
        while queue and pages < max_pages:
            url = queue.pop(0)
            if url in visited: 
                continue
            try:
                resp = client.get(url)
            except Exception:
                pages += 1; pbar.update(1); continue

            visited.add(url); pages += 1; pbar.update(1)
            html = resp.text
            ctx = classify_page_context(html, url)  # <- 关键：判别页面类型
            is_category = ctx["is_category"]
            is_product  = ctx["is_product"]
            gender = ctx.get("gender")
            cats   = ctx.get("categories") or []

            # 仅在“类目/列表页”上记录产品来源 & 抽取详情链接
            if is_category:
                detail_links = discover_product_links_from_html(html, client.settings.base_url)
                for href in detail_links:
                    absu = urljoin(client.settings.base_url, href) if href.startswith("/") else href
                    norm = normalize_url(absu)
                    product_urls.add(norm)
                    # 把该产品“来自哪个 Men/Women + 类目列表页”写进 found_in
                    if not cats:
                        # 没识别到明确类目时，记录一个 category=None 也可（可视化时可过滤）
                        product_contexts.setdefault(norm, []).append({
                            "gender": gender or None,
                            "category": None,
                            "source_url": url,
                        })
                    else:
                        for c in cats:
                            product_contexts.setdefault(norm, []).append({
                                "gender": gender or None,
                                "category": c,
                                "source_url": url,
                            })

            # 扩展新的“探索页”：只扩展可能是类目/列表的 URL，避免把详情页当入口
            if is_category:
                soup = soupify(html)
                expand_links=[]
                for a in soup.select("a[href]"):
                    h=a.get("href",""); 
                    if not h or h.startswith("#"): continue
                    if h.startswith("/"): h=urljoin(client.settings.base_url, h)
                    if urlparse(h).netloc.lower()!=urlparse(client.settings.base_url).netloc.lower(): 
                        continue
                    low=h.lower()
                    if any(x in low for x in CATEGORY_DENY): 
                        continue
                    # 具有“列表/类目页”的外观：带 men/women 或带类目词 或 ?page=
                    if ("?page=" in low) or ("men" in low) or ("women" in low) or any(
                        kw in low for kw in [
                            "jacket","pant","goggle","fleece","base","hoodie","t-shirt","beanie",
                            "glove","helmet","mask","sock","backpack","outerwear","facemask"
                        ]
                    ):
                        expand_links.append(h)
                for link in expand_links[:50]:
                    if link not in visited:
                        queue.append(link)

    print(f"  Discovered product URL candidates: {len(product_urls)}")

    # 解析 + 合并（按 canonical URL）
    products_by_key: Dict[str, Dict] = {}
    for purl in tqdm(sorted(product_urls), desc="Parsing products", unit="product"):
        try:
            resp = client.get(purl)
            pdata = parse_product_page(resp.text, purl)
            if not (pdata.get("name") or (pdata.get("price") is not None)):
                continue
            key = normalize_url(pdata.get("canonical_url") or purl)
            if key not in products_by_key:
                products_by_key[key] = pdata
                products_by_key[key]["found_in"] = []
            # 合并 found_in（只来自类目/列表页）
            products_by_key[key]["found_in"].extend(product_contexts.get(purl, []))
            products_by_key[key]["found_in"].extend(product_contexts.get(key, []))
        except Exception:
            continue

    # 清洗 found_in，并输出 gender / categories
    result = []
    for key, prod in products_by_key.items():
        # 去重 found_in
        seen = set(); fin=[]
        for r in prod.get("found_in", []):
            tup = (r.get("gender"), r.get("category"), r.get("source_url"))
            if tup not in seen:
                seen.add(tup); fin.append(r)
        prod["found_in"] = fin

        # 汇总 gender
        gvals = [x.get("gender") for x in fin if x.get("gender")]
        if gvals:
            men = sum(1 for x in gvals if x == "men")
            women = sum(1 for x in gvals if x == "women")
            prod["gender"] = "both" if (men and women) else ("men" if men else ("women" if women else "unknown"))
        else:
            prod["gender"] = "unknown"

        # 汇总 categories（found_in 的 category + 详情页自身解析到的）
        cat_from_fin = [x.get("category") for x in fin if x.get("category")]
        all_cats = (prod.get("categories") or []) + cat_from_fin
        clean=[]; seen=set()
        for c in all_cats:
            c = (c or "").strip()
            if not c: continue
            if c.lower() in ("home","shop","bestsellers","new-arrivals","sale"): 
                continue
            if c not in seen:
                seen.add(c); clean.append(c)
        prod["categories"] = clean

        result.append(prod)

    return result
