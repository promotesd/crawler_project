# src/cli.py
import argparse
from config import Settings
from httpclient import HttpClient
from menu import crawl_menu
from products import crawl_products
from saver import write_site_json_single, write_site_csv_single

def main(argv=None):
    parser = argparse.ArgumentParser(description="Dopesnow crawler (single-file output)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_crawl = sub.add_parser("crawl", help="Crawl menu & products into ONE file")
    p_crawl.add_argument("--base", default="https://www.dopesnow.com/", help="Base URL")
    p_crawl.add_argument("--delay", type=float, default=1.2, help="Delay seconds between requests")
    p_crawl.add_argument("--pages", type=int, default=200, help="Max seed pages to explore for discovery")
    p_crawl.add_argument("--format", choices=["csv", "json"], default="csv", help="Output format (single file)")
    p_crawl.add_argument("--out", default=None, help="Output path. Default: data/site_dump.csv or data/site_dump.json")

    args = parser.parse_args(argv)

    if args.cmd == "crawl":
        settings = Settings(base_url=args.base, delay_seconds=args.delay)

        client = HttpClient(settings)

        print("[1/3] Crawling menu...")
        menu_rows = crawl_menu(client)
        print(f"  menu: {len(menu_rows)} items")

        print("[2/3] Building seeds from menu + home...")
        seeds = [settings.base_url] + [r["url"] for r in menu_rows]

        print("[3/3] Crawling products (discovery + detail parse)...")
        products = crawl_products(client, seeds=seeds, max_pages=args.pages)

        # 输出路径
        out_path = args.out
        if not out_path:
            out_path = "data/dopesnow_site_product.json" if args.format == "json" else "data/dopesnow_site_product.csv"

        # 单文件写出
        if args.format == "json":
            write_site_json_single(out_path, menu_rows, products)
        else:
            write_site_csv_single(out_path, menu_rows, products)

        print(f"Done. Wrote -> {out_path}")

if __name__ == "__main__":
    main()
