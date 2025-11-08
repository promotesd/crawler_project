# src/cli.py
import argparse
from config import Settings
from httpclient import HttpClient
from menu import crawl_menu   # 仍可保留；抓不到菜单也不影响
from products import crawl_products
from saver import write_site_json_single, write_site_csv_single

def main(argv=None):
    parser = argparse.ArgumentParser(description="Dopesnow crawler (single-file output, with category provenance)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("crawl")
    p.add_argument("--base", default="https://www.dopesnow.com/", help="Base URL")
    p.add_argument("--delay", type=float, default=1.2, help="Delay seconds")
    p.add_argument("--pages", type=int, default=1500, help="Max pages to explore")
    p.add_argument("--format", choices=["json","csv"], default="json")
    p.add_argument("--out", default=None)
    p.add_argument("--seeds", default="", help="Comma-separated extra seed URLs")

    args = parser.parse_args(argv)

    settings = Settings(base_url=args.base, delay_seconds=args.delay)
    client = HttpClient(settings)

    print("[1/3] Crawling menu...")
    menu_rows = crawl_menu(client)
    print(f"  menu: {len(menu_rows)} items")

    print("[2/3] Building seeds from menu + home...")
    extra_seeds = [s.strip() for s in args.seeds.split(",") if s.strip()]
    seeds = [settings.base_url] + [r["url"] for r in menu_rows] + extra_seeds

    print("[3/3] Crawling products (discovery + detail parse)...")
    products = crawl_products(client, seeds=seeds, max_pages=args.pages)

    out_path = args.out or ("data/dopesnow_site_product.json" if args.format=="json" else "data/dopesnow_site_product.csv")
    if args.format == "json":
        write_site_json_single(out_path, menu_rows, products)
    else:
        write_site_csv_single(out_path, menu_rows, products)
    print(f"Done. Wrote -> {out_path}")

if __name__ == "__main__":
    main()

