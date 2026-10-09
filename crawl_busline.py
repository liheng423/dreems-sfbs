"""Crawl one GTFS route into data/buslines/<route>/.

Example: python crawl_busline.py --route 605
"""

from src.crawler.busline.crawl_gtfs import main


if __name__ == "__main__":
    main()
