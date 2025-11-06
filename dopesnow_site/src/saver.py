# src/saver.py
import os, csv, json
from typing import List, Dict, Literal

def ensure_dir(path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)

def write_site_json_single(out_path: str, menu_rows: List[Dict[str, str]], products: List[Dict]) -> None:
    """写出一个 JSON 文件：{menu: [...], products: [...]}"""
    ensure_dir(out_path)
    payload = {
        "menu": menu_rows,
        "products": products,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

def write_site_csv_single(out_path: str, menu_rows: List[Dict[str, str]], products: List[Dict]) -> None:
    """
    写出一个 CSV 文件，一张表存两类记录：
      - 菜单行：record_type=menu, 字段 text, url
      - 商品行：record_type=product, 字段 url, name, price, priceCurrency, sku, brand, description, images(json)
    其余列为空。
    """
    ensure_dir(out_path)
    # 统一所有可能用到的列（为了“一个完整的表”）
    fieldnames = [
        "record_type",        # menu 或 product
        # menu
        "text", "menu_url",
        # product
        "product_url", "name", "price", "priceCurrency", "sku", "brand", "description", "images",
    ]
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()

        # 菜单 -> 一行一个链接
        for m in menu_rows:
            w.writerow({
                "record_type": "menu",
                "text": m.get("text", ""),
                "menu_url": m.get("url", ""),
                # 其余留空
            })

        # 商品 -> 一行一个商品
        for p in products:
            # images 放在一个单元格，使用 JSON 字符串，避免多表
            images_cell = json.dumps(p.get("images", []), ensure_ascii=False)
            w.writerow({
                "record_type": "product",
                "product_url": p.get("url", ""),
                "name": p.get("name", ""),
                "price": p.get("price", ""),
                "priceCurrency": p.get("priceCurrency", ""),
                "sku": p.get("sku", ""),
                "brand": p.get("brand", ""),
                "description": p.get("description", ""),
                "images": images_cell,
            })
