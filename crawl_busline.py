"""Extract one scheduled GTFS route into outputs/buslines/<name>/.

Example: python crawl_busline.py --gtfs-zip feed.zip --service-date 2026-10-19 --route 12
"""

from src.crawler.busline.crawl_gtfs import main


if __name__ == "__main__":
    main()
