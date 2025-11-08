# src/saver.py
import os, csv, json
from typing import List, Dict

def ensure_dir(path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)

def write_site_json_single(out_path: str, menu_rows: List[Dict[str, str]], products: List[Dict]) -> None:
    ensure_dir(out_path)
    payload = {"menu": menu_rows, "products": products}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

def write_site_csv_single(out_path: str, menu_rows: List[Dict[str, str]], products: List[Dict]) -> None:
    ensure_dir(out_path)
    fieldnames = [
        "record_type",
        "text","menu_url",
        "product_url","canonical_url","name","price","priceCurrency","sku","brand","description","images",
        "gender","categories","found_in",
    ]
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for m in menu_rows:
            w.writerow({
                "record_type":"menu","text":m.get("text",""),"menu_url":m.get("url","")
            })
        import json as _json
        for p in products:
            w.writerow({
                "record_type":"product",
                "product_url":p.get("url",""),
                "canonical_url":p.get("canonical_url",""),
                "name":p.get("name",""),
                "price":p.get("price",""),
                "priceCurrency":p.get("priceCurrency",""),
                "sku":p.get("sku",""),
                "brand":p.get("brand",""),
                "description":p.get("description",""),
                "images":_json.dumps(p.get("images",[]), ensure_ascii=False),
                "gender":p.get("gender",""),
                "categories":_json.dumps(p.get("categories",[]), ensure_ascii=False),
                "found_in":_json.dumps(p.get("found_in",[]), ensure_ascii=False),
            })
