from pathlib import Path

import pytest

from src.scraper import MediaWikiScraper


def test_safe_filename():

    result = (
        MediaWikiScraper.safe_filename(
            'Character: "Columbina"?'
        )
    )

    assert ":" not in result
    assert '"' not in result
    assert "?" not in result


def test_normalize_category():

    result = (
        MediaWikiScraper.normalize_category_name(
            "Characters"
        )
    )

    assert result == "Category:Characters"


def test_existing_category_prefix():

    result = (
        MediaWikiScraper.normalize_category_name(
            "Category:Characters"
        )
    )

    assert result == "Category:Characters"


def test_empty_category():

    with pytest.raises(
        ValueError
    ):

        MediaWikiScraper.normalize_category_name(
            ""
        )