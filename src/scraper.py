"""
MediaWiki / Fandom ingestion module.

Responsibilities
----------------
1. Connect to a MediaWiki Action API endpoint.
2. Retrieve raw article wikitext.
3. Retrieve article metadata.
4. Enumerate category members.
5. Follow MediaWiki continuation tokens.
6. Crawl categories recursively.
7. Retry temporary network/server failures.
8. Save raw pages as structured JSON.
9. Produce crawl manifests for reproducibility.

The output from this module is intentionally RAW.
Cleaning and wikitext normalization happen later in cleaner.py.
"""

from __future__ import annotations

import json
import re
import time

from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import requests

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import RAW_DATA_DIR, settings


# ============================================================
# CUSTOM EXCEPTIONS
# ============================================================


class MediaWikiError(RuntimeError):
    """
    Base exception for MediaWiki-related failures.
    """


class MediaWikiAPIError(MediaWikiError):
    """
    Raised when MediaWiki returns an API-level error.
    """


class PageNotFoundError(MediaWikiError):
    """
    Raised when a requested wiki page does not exist.
    """


# ============================================================
# MEDIAWIKI SCRAPER
# ============================================================


class MediaWikiScraper:
    """
    Reusable MediaWiki / Fandom crawler.

    Parameters
    ----------
    api_url:
        Full MediaWiki API endpoint.

        Example:
        https://genshin-impact.fandom.com/api.php

    output_dir:
        Directory where raw page JSON files are stored.

    user_agent:
        Descriptive HTTP User-Agent.

    timeout:
        Request timeout in seconds.

    request_delay:
        Minimum delay between API calls.

    max_retries:
        Maximum number of HTTP retry attempts.

    maxlag:
        MediaWiki maxlag value.
    """

    def __init__(
        self,
        api_url: str | None = None,
        output_dir: Path | str = RAW_DATA_DIR,
        user_agent: str | None = None,
        timeout: int | None = None,
        request_delay: float | None = None,
        max_retries: int | None = None,
        maxlag: int | None = None,
    ) -> None:

        # Validate the MediaWiki settings only when this
        # component is actually instantiated.
        settings.validate_mediawiki()

        self.api_url = (
            api_url
            or settings.mediawiki_api_url
        )

        self.output_dir = Path(output_dir)

        self.user_agent = (
            user_agent
            or settings.mediawiki_user_agent
        )

        self.timeout = (
            timeout
            if timeout is not None
            else settings.request_timeout
        )

        self.request_delay = (
            request_delay
            if request_delay is not None
            else settings.request_delay_seconds
        )

        self.max_retries = (
            max_retries
            if max_retries is not None
            else settings.max_retries
        )

        self.maxlag = (
            maxlag
            if maxlag is not None
            else settings.mediawiki_maxlag
        )

        self.output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.session = self._create_session()

        self._last_request_time = 0.0

    # ========================================================
    # SESSION / NETWORKING
    # ========================================================

    def _create_session(self) -> requests.Session:
        """
        Create a reusable requests Session.

        HTTP retries are enabled for temporary failures such as:
        - 429 Too Many Requests
        - 500 Internal Server Error
        - 502 Bad Gateway
        - 503 Service Unavailable
        - 504 Gateway Timeout
        """

        session = requests.Session()

        retry_strategy = Retry(
            total=self.max_retries,
            connect=self.max_retries,
            read=self.max_retries,
            status=self.max_retries,

            backoff_factor=1.0,

            status_forcelist=[
                429,
                500,
                502,
                503,
                504,
            ],

            allowed_methods=frozenset(
                ["GET"]
            ),

            respect_retry_after_header=True,
        )

        adapter = HTTPAdapter(
            max_retries=retry_strategy
        )

        session.mount(
            "https://",
            adapter,
        )

        session.mount(
            "http://",
            adapter,
        )

        session.headers.update(
            {
                "User-Agent": self.user_agent,
                "Accept": "application/json",
            }
        )

        return session

    def _respect_request_delay(self) -> None:
        """
        Enforce a minimum interval between requests.

        This avoids hammering the wiki API.
        """

        if self.request_delay <= 0:
            return

        elapsed = (
            time.monotonic()
            - self._last_request_time
        )

        remaining = (
            self.request_delay
            - elapsed
        )

        if remaining > 0:
            time.sleep(remaining)

    def _request(
        self,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Execute one MediaWiki API request.

        Common parameters such as JSON output and maxlag
        are injected automatically.
        """

        base_params = {
            "format": "json",
            "formatversion": "2",
            "maxlag": self.maxlag,
        }

        request_params = {
            **base_params,
            **params,
        }

        # maxlag can produce an API-level error even when
        # the HTTP request itself succeeds, so it is retried
        # separately here.
        maxlag_attempt = 0

        while True:

            self._respect_request_delay()

            try:

                response = self.session.get(
                    self.api_url,
                    params=request_params,
                    timeout=self.timeout,
                )

                self._last_request_time = (
                    time.monotonic()
                )

                response.raise_for_status()

            except requests.RequestException as exc:

                raise MediaWikiAPIError(
                    f"MediaWiki request failed: {exc}"
                ) from exc

            try:

                payload = response.json()

            except ValueError as exc:

                raise MediaWikiAPIError(
                    "MediaWiki returned an invalid "
                    "JSON response."
                ) from exc

            error = payload.get("error")

            if not error:
                return payload

            error_code = error.get(
                "code",
                "unknown",
            )

            error_info = error.get(
                "info",
                "Unknown MediaWiki error",
            )

            # MediaWiki may ask clients to back off when
            # replication lag is too high.
            if (
                error_code == "maxlag"
                and maxlag_attempt < self.max_retries
            ):

                maxlag_attempt += 1

                wait_seconds = min(
                    2 ** maxlag_attempt,
                    30,
                )

                time.sleep(wait_seconds)

                continue

            raise MediaWikiAPIError(
                f"MediaWiki API error "
                f"[{error_code}]: {error_info}"
            )

    # ========================================================
    # SITE INFORMATION
    # ========================================================

    def get_site_info(
        self,
    ) -> dict[str, Any]:
        """
        Retrieve basic information about the target wiki.

        Useful for verifying that MEDIAWIKI_API_URL points
        to a valid MediaWiki installation.
        """

        payload = self._request(
            {
                "action": "query",
                "meta": "siteinfo",
                "siprop": "general",
            }
        )

        general = (
            payload
            .get("query", {})
            .get("general", {})
        )

        return {
            "sitename": general.get(
                "sitename"
            ),

            "lang": general.get(
                "lang"
            ),

            "server": general.get(
                "server"
            ),

            "articlepath": general.get(
                "articlepath"
            ),

            "scriptpath": general.get(
                "scriptpath"
            ),

            "generator": general.get(
                "generator"
            ),
        }

    # ========================================================
    # PAGE INGESTION
    # ========================================================

    def get_page(
        self,
        title: str,
    ) -> dict[str, Any]:
        """
        Retrieve the latest revision and raw wikitext for a
        wiki article.

        Redirects are resolved automatically.
        """

        title = title.strip()

        if not title:
            raise ValueError(
                "Page title cannot be empty."
            )

        payload = self._request(
            {
                "action": "query",

                "prop": (
                    "info|revisions"
                ),

                "titles": title,

                "inprop": "url",

                "redirects": 1,

                "rvprop": (
                    "ids|timestamp|sha1|"
                    "content|contentmodel"
                ),

                "rvslots": "main",

                "rvlimit": 1,
            }
        )

        pages = (
            payload
            .get("query", {})
            .get("pages", [])
        )

        if not pages:
            raise PageNotFoundError(
                f"No page returned for '{title}'."
            )

        page = pages[0]

        if page.get("missing") is not None:
            raise PageNotFoundError(
                f"Page '{title}' was not found."
            )

        revisions = page.get(
            "revisions",
            [],
        )

        if not revisions:
            raise MediaWikiAPIError(
                f"Page '{title}' contains "
                "no accessible revision."
            )

        revision = revisions[0]

        slots = revision.get(
            "slots",
            {},
        )

        main_slot = slots.get(
            "main",
            {},
        )

        # Modern MediaWiki API
        content = main_slot.get(
            "content"
        )

        # Compatibility fallback used by some older
        # MediaWiki installations.
        if content is None:
            content = main_slot.get("*")

        if content is None:
            content = revision.get("*")

        if content is None:
            raise MediaWikiAPIError(
                f"Could not extract content "
                f"from '{title}'."
            )

        retrieved_at = (
            datetime.now(timezone.utc)
            .isoformat()
        )

        record = {
            "schema_version": "1.0",

            "source": {
                "type": "mediawiki",
                "api_url": self.api_url,
            },

            "page": {
                "requested_title": title,

                "page_id": page.get(
                    "pageid"
                ),

                "title": page.get(
                    "title"
                ),

                "namespace": page.get(
                    "ns"
                ),

                "url": page.get(
                    "fullurl"
                ),

                "length": page.get(
                    "length"
                ),

                "touched": page.get(
                    "touched"
                ),

                "last_revision_id": page.get(
                    "lastrevid"
                ),
            },

            "revision": {
                "revision_id": revision.get(
                    "revid"
                ),

                "parent_revision_id": (
                    revision.get(
                        "parentid"
                    )
                ),

                "timestamp": revision.get(
                    "timestamp"
                ),

                "sha1": revision.get(
                    "sha1"
                ),

                "content_model": (
                    main_slot.get(
                        "contentmodel"
                    )
                    or revision.get(
                        "contentmodel"
                    )
                ),
            },

            "retrieved_at": retrieved_at,

            "content": content,
        }

        return record

    # ========================================================
    # CATEGORY ENUMERATION
    # ========================================================

    @staticmethod
    def normalize_category_name(
        category: str,
    ) -> str:
        """
        Ensure a category title starts with 'Category:'.
        """

        category = category.strip()

        if not category:
            raise ValueError(
                "Category name cannot be empty."
            )

        if not category.lower().startswith(
            "category:"
        ):
            category = (
                f"Category:{category}"
            )

        return category

    def get_category_members(
        self,
        category: str,
        include_subcategories: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Retrieve every member of a MediaWiki category.

        MediaWiki returns large lists in batches. This method
        automatically follows the returned continuation token.
        """

        category = (
            self.normalize_category_name(
                category
            )
        )

        members: list[
            dict[str, Any]
        ] = []

        continuation: dict[
            str,
            Any
        ] = {}

        while True:

            params = {
                "action": "query",

                "list": "categorymembers",

                "cmtitle": category,

                "cmlimit": "max",

                "cmprop": (
                    "ids|title|type|timestamp"
                ),

                "cmtype": (
                    "page|subcat"
                    if include_subcategories
                    else "page"
                ),
            }

            params.update(
                continuation
            )

            payload = self._request(
                params
            )

            batch = (
                payload
                .get("query", {})
                .get(
                    "categorymembers",
                    [],
                )
            )

            members.extend(
                batch
            )

            next_continue = (
                payload.get("continue")
            )

            if not next_continue:
                break

            continuation = (
                next_continue
            )

        return members

    # ========================================================
    # FILE STORAGE
    # ========================================================

    @staticmethod
    def safe_filename(
        value: str,
        max_length: int = 120,
    ) -> str:
        """
        Convert a wiki title into a filesystem-safe string.

        Important for Windows because characters such as
        :, *, ?, <, > and | cannot appear in filenames.
        """

        value = value.strip()

        value = re.sub(
            r'[<>:"/\\|?*\x00-\x1f]',
            "_",
            value,
        )

        value = re.sub(
            r"\s+",
            "_",
            value,
        )

        value = re.sub(
            r"_+",
            "_",
            value,
        )

        value = value.strip(
            "._ "
        )

        if not value:
            value = "untitled"

        return value[:max_length]

    def page_output_path(
        self,
        record: dict[str, Any],
    ) -> Path:
        """
        Generate a stable file path for an article.

        Page ID is included to prevent filename collisions.
        """

        page = record["page"]

        page_id = (
            page.get("page_id")
            or "unknown"
        )

        title = (
            page.get("title")
            or page.get("requested_title")
            or "untitled"
        )

        safe_title = self.safe_filename(
            title
        )

        filename = (
            f"{page_id}_{safe_title}.json"
        )

        return (
            self.output_dir
            / filename
        )

    def save_page(
        self,
        record: dict[str, Any],
        overwrite: bool = False,
    ) -> Path:
        """
        Persist a raw page record to JSON.

        The write is performed through a temporary file and
        then renamed to reduce the chance of leaving a
        half-written JSON file if execution is interrupted.
        """

        output_path = (
            self.page_output_path(
                record
            )
        )

        if (
            output_path.exists()
            and not overwrite
        ):
            return output_path

        temporary_path = (
            output_path.with_name(
                output_path.name
                + ".tmp"
            )
        )

        with temporary_path.open(
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                record,
                file,
                ensure_ascii=False,
                indent=2,
            )

        temporary_path.replace(
            output_path
        )

        return output_path

    # ========================================================
    # MULTIPLE PAGE INGESTION
    # ========================================================

    def crawl_titles(
        self,
        titles: Iterable[str],
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """
        Crawl a list of explicitly supplied page titles.
        """

        results: list[
            dict[str, Any]
        ] = []

        failures: list[
            dict[str, str]
        ] = []

        for title in titles:

            title = title.strip()

            if not title:
                continue

            try:

                record = self.get_page(
                    title
                )

                output_path = (
                    self.save_page(
                        record,
                        overwrite=overwrite,
                    )
                )

                results.append(
                    {
                        "title": (
                            record["page"][
                                "title"
                            ]
                        ),

                        "page_id": (
                            record["page"][
                                "page_id"
                            ]
                        ),

                        "revision_id": (
                            record[
                                "revision"
                            ][
                                "revision_id"
                            ]
                        ),

                        "file": str(
                            output_path
                        ),
                    }
                )

            except (
                MediaWikiError,
                requests.RequestException,
            ) as exc:

                failures.append(
                    {
                        "title": title,
                        "error": str(exc),
                    }
                )

        return {
            "pages_saved": len(
                results
            ),

            "pages_failed": len(
                failures
            ),

            "pages": results,

            "failures": failures,
        }

    # ========================================================
    # CATEGORY CRAWLING
    # ========================================================

    def crawl_category(
        self,
        category: str,
        recursive: bool = False,
        max_depth: int = 1,
        max_pages: int | None = None,
        namespaces: tuple[int, ...] = (0,),
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """
        Crawl articles belonging to a MediaWiki category.

        Parameters
        ----------
        category:
            Category name.

        recursive:
            Whether child categories should also be crawled.

        max_depth:
            Maximum recursive category depth.

            0 = only supplied category
            1 = supplied category + direct subcategories
            2 = two levels below, etc.

        max_pages:
            Optional safety limit.

            None means no page limit.

        namespaces:
            Article namespaces that should be saved.

            Namespace 0 represents normal wiki articles.

        overwrite:
            Replace existing raw JSON files.
        """

        category = (
            self.normalize_category_name(
                category
            )
        )

        if max_depth < 0:
            raise ValueError(
                "max_depth cannot be negative."
            )

        if (
            max_pages is not None
            and max_pages <= 0
        ):
            raise ValueError(
                "max_pages must be greater "
                "than 0 or None."
            )

        category_queue = deque(
            [
                (
                    category,
                    0,
                )
            ]
        )

        visited_categories: set[
            str
        ] = set()

        visited_pages: set[
            int | str
        ] = set()

        stored_pages: list[
            dict[str, Any]
        ] = []

        failures: list[
            dict[str, str]
        ] = []

        stop_crawl = False

        while (
            category_queue
            and not stop_crawl
        ):

            (
                current_category,
                depth,
            ) = category_queue.popleft()

            if (
                current_category
                in visited_categories
            ):
                continue

            visited_categories.add(
                current_category
            )

            try:

                members = (
                    self.get_category_members(
                        current_category,
                        include_subcategories=(
                            recursive
                        ),
                    )
                )

            except MediaWikiError as exc:

                failures.append(
                    {
                        "title": (
                            current_category
                        ),
                        "error": str(exc),
                    }
                )

                continue

            for member in members:

                member_type = (
                    member.get(
                        "type"
                    )
                )

                namespace = (
                    member.get(
                        "ns"
                    )
                )

                member_title = (
                    member.get(
                        "title"
                    )
                )

                # ----------------------------
                # SUBCATEGORY
                # ----------------------------

                is_subcategory = (
                    member_type == "subcat"
                    or namespace == 14
                )

                if is_subcategory:

                    if (
                        recursive
                        and depth < max_depth
                        and member_title
                    ):

                        category_queue.append(
                            (
                                member_title,
                                depth + 1,
                            )
                        )

                    continue

                # ----------------------------
                # PAGE FILTER
                # ----------------------------

                if (
                    namespace
                    not in namespaces
                ):
                    continue

                page_identifier = (
                    member.get(
                        "pageid"
                    )
                    or member_title
                )

                if (
                    page_identifier
                    in visited_pages
                ):
                    continue

                visited_pages.add(
                    page_identifier
                )

                try:

                    record = (
                        self.get_page(
                            member_title
                        )
                    )

                    output_path = (
                        self.save_page(
                            record,
                            overwrite=overwrite,
                        )
                    )

                    stored_pages.append(
                        {
                            "title": (
                                record[
                                    "page"
                                ][
                                    "title"
                                ]
                            ),

                            "page_id": (
                                record[
                                    "page"
                                ][
                                    "page_id"
                                ]
                            ),

                            "revision_id": (
                                record[
                                    "revision"
                                ][
                                    "revision_id"
                                ]
                            ),

                            "category": (
                                current_category
                            ),

                            "depth": depth,

                            "file": str(
                                output_path
                            ),
                        }
                    )

                except MediaWikiError as exc:

                    failures.append(
                        {
                            "title": (
                                member_title
                            ),
                            "error": str(
                                exc
                            ),
                        }
                    )

                if (
                    max_pages is not None
                    and len(
                        stored_pages
                    ) >= max_pages
                ):

                    stop_crawl = True
                    break

        summary = {
            "schema_version": "1.0",

            "crawl": {
                "root_category": category,

                "recursive": recursive,

                "max_depth": max_depth,

                "max_pages": max_pages,

                "namespaces": list(
                    namespaces
                ),

                "started_from_api": (
                    self.api_url
                ),

                "completed_at": (
                    datetime.now(
                        timezone.utc
                    ).isoformat()
                ),
            },

            "statistics": {
                "categories_visited": len(
                    visited_categories
                ),

                "pages_saved": len(
                    stored_pages
                ),

                "pages_failed": len(
                    failures
                ),
            },

            "categories": sorted(
                visited_categories
            ),

            "pages": stored_pages,

            "failures": failures,
        }

        manifest_path = (
            self.save_manifest(
                category,
                summary,
            )
        )

        summary[
            "manifest"
        ] = str(
            manifest_path
        )

        return summary

    # ========================================================
    # MANIFEST
    # ========================================================

    def save_manifest(
        self,
        crawl_name: str,
        manifest: dict[str, Any],
    ) -> Path:
        """
        Save metadata describing one crawl run.
        """

        safe_name = self.safe_filename(
            crawl_name
        )

        timestamp = (
            datetime.now(
                timezone.utc
            )
            .strftime(
                "%Y%m%dT%H%M%SZ"
            )
        )

        filename = (
            f"manifest_"
            f"{safe_name}_"
            f"{timestamp}.json"
        )

        path = (
            self.output_dir
            / filename
        )

        with path.open(
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                manifest,
                file,
                ensure_ascii=False,
                indent=2,
            )

        return path

    # ========================================================
    # CLEANUP
    # ========================================================

    def close(self) -> None:
        """
        Close the underlying HTTP session.
        """

        self.session.close()

    def __enter__(
        self,
    ) -> "MediaWikiScraper":
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ) -> None:
        self.close()