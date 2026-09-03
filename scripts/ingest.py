"""
Command-line ingestion utility for Akashic-RAG.

Examples
--------

Check wiki:

python -m scripts.ingest --site-info


Download one page:

python -m scripts.ingest --page "Columbina"


Download several pages:

python -m scripts.ingest \
    --page "Columbina" \
    --page "Pierro"


Crawl category:

python -m scripts.ingest \
    --category "Characters"


Recursive category crawl:

python -m scripts.ingest \
    --category "Characters" \
    --recursive \
    --max-depth 1 \
    --max-pages 50
"""

import argparse
import json
import sys

from src.scraper import (
    MediaWikiError,
    MediaWikiScraper,
)


def create_parser() -> argparse.ArgumentParser:
    """
    Create command-line argument parser.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Akashic-RAG MediaWiki/Fandom ingestion tool"
        )
    )

    mode = parser.add_mutually_exclusive_group(
        required=True
    )

    mode.add_argument(
        "--site-info",
        action="store_true",
        help="Check the configured MediaWiki endpoint.",
    )

    mode.add_argument(
        "--page",
        action="append",
        help=(
            "Download a page. Can be specified "
            "multiple times."
        ),
    )

    mode.add_argument(
        "--category",
        type=str,
        help="Crawl pages from a category.",
    )

    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Also crawl nested subcategories.",
    )

    parser.add_argument(
        "--max-depth",
        type=int,
        default=1,
        help=(
            "Maximum recursive category depth. "
            "Default: 1"
        ),
    )

    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help=(
            "Maximum number of pages to download."
        ),
    )

    parser.add_argument(
        "--overwrite",
        action="store_true",
        help=(
            "Overwrite existing raw page JSON files."
        ),
    )

    return parser


def main() -> None:

    parser = create_parser()

    args = parser.parse_args()

    try:

        with MediaWikiScraper() as scraper:

            # ==================================================
            # SITE TEST
            # ==================================================

            if args.site_info:

                info = (
                    scraper.get_site_info()
                )

                print(
                    json.dumps(
                        info,
                        indent=2,
                        ensure_ascii=False,
                    )
                )

                return

            # ==================================================
            # PAGE MODE
            # ==================================================

            if args.page:

                result = (
                    scraper.crawl_titles(
                        args.page,
                        overwrite=(
                            args.overwrite
                        ),
                    )
                )

                print(
                    json.dumps(
                        result,
                        indent=2,
                        ensure_ascii=False,
                    )
                )

                return

            # ==================================================
            # CATEGORY MODE
            # ==================================================

            if args.category:

                result = (
                    scraper.crawl_category(
                        category=(
                            args.category
                        ),

                        recursive=(
                            args.recursive
                        ),

                        max_depth=(
                            args.max_depth
                        ),

                        max_pages=(
                            args.max_pages
                        ),

                        overwrite=(
                            args.overwrite
                        ),
                    )
                )

                print(
                    json.dumps(
                        result,
                        indent=2,
                        ensure_ascii=False,
                    )
                )

                return

    except MediaWikiError as exc:

        print(
            f"\nMediaWiki error: {exc}",
            file=sys.stderr,
        )

        raise SystemExit(1)

    except KeyboardInterrupt:

        print(
            "\nCrawl cancelled."
        )

        raise SystemExit(130)


if __name__ == "__main__":
    main()