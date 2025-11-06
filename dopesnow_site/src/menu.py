# src/menu.py
from typing import List, Dict
from urllib.parse import urljoin
from httpclient import HttpClient
from parse import parse_menu

def crawl_menu(client: HttpClient) -> List[Dict[str, str]]:
    r = client.get(client.settings.base_url)
    items = parse_menu(r.text, client.settings.base_url)
    out = []
    for it in items:
        href = it["href"]
        if href.startswith("/"):
            href = urljoin(client.settings.base_url, href)
        out.append({"text": it["text"], "url": href})
    return out
