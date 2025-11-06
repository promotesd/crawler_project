# src/products.py
from typing import List, Dict, Set
from urllib.parse import urljoin
from tqdm import tqdm

from httpclient import HttpClient
from parse import discover_product_links_from_html, parse_product_page

def crawl_products(client: HttpClient, seeds: List[str], max_pages: int = 200) -> List[Dict]:
    """
    两段进度条：
      1) Discovering pages: 以 max_pages 为上限，展示页面发现进度
      2) Parsing products: 以候选商品链接数为总量，展示解析进度
    """
    visited: Set[str] = set()
    product_urls: Set[str] = set()
    queue: List[str] = []

    # 初始化 frontier
    for s in seeds:
        if s.startswith("/"):
            s = urljoin(client.settings.base_url, s)
        queue.append(s)

    # 1) 发现阶段（BFS），进度条按“已处理页面数/上限”展示
    pages = 0
    with tqdm(total=max_pages, desc="Discovering pages", unit="page") as pbar:
        while queue and pages < max_pages:
            url = queue.pop(0)
            if url in visited:
                continue
            try:
                resp = client.get(url)
            except Exception:
                # 忽略临时失败，继续
                pbar.update(1)
                pages += 1
                continue
            visited.add(url)
            pages += 1
            pbar.update(1)

            html = resp.text
            # 发现疑似商品链接
            candidates = discover_product_links_from_html(html, client.settings.base_url)
            for href in candidates:
                absu = urljoin(client.settings.base_url, href)
                product_urls.add(absu)
            # 轻度扩展：把部分候选也入队，扩大覆盖面但防止爆炸
            for a in candidates[:5]:
                queue.append(urljoin(client.settings.base_url, a))

    # 发现结果提示
    print(f"  Discovered product URL candidates: {len(product_urls)}")

    # 2) 解析阶段（逐个商品页解析），进度条按“商品数”展示
    products: List[Dict] = []
    sorted_urls = sorted(product_urls)
    for purl in tqdm(sorted_urls, desc="Parsing products", unit="product"):
        try:
            resp = client.get(purl)
            pdata = parse_product_page(resp.text, purl)
            # 若页面没有拿到任何合理字段，则丢弃
            if pdata.get("name") or pdata.get("price"):
                products.append(pdata)
        except Exception:
            continue

    return products
