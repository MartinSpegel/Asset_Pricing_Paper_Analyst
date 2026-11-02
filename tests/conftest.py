import pytest

from paper_analyst.filters import SearchQuery
from paper_analyst.http import MockTransport
from paper_analyst.models import Paper
from paper_analyst.storage import Store


@pytest.fixture
def transport():
    return MockTransport()


@pytest.fixture
def store():
    s = Store(":memory:")
    yield s
    s.close()


@pytest.fixture
def broad_query():
    return SearchQuery(topics=["sdf", "return_predictability", "transfer_learning",
                               "international_asset_pricing", "machine_learning"])


@pytest.fixture
def sample_paper():
    return Paper(
        title="Transfer Learning for Stochastic Discount Factors",
        authors=["Ada Lindqvist"],
        abstract=("We study whether transfer learning improves SDF estimation in international markets. "
                  "Our sample covers stocks in 10 countries from 2000 to 2020. "
                  "We find that pricing errors fall by 10%. "
                  "However, gains are small in large markets."),
        publication_date="2024-01-01", doi="10.5555/test.1", sources=["openalex"])
