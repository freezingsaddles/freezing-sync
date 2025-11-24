import json
import os
from unittest.mock import MagicMock, patch

import pytest
from stravalib.client import Client
from stravalib.model import DetailedActivity, Stream

from freezing.sync.utils.cache import (
    CachingActivityFetcher,
    CachingAthleteObjectFetcher,
    CachingStreamFetcher,
)


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def cache_basedir(tmpdir):
    return str(tmpdir)


class TestCachingAthleteObjectFetcher:
    def test_cache_object_json(self, cache_basedir, client):
        fetcher = CachingActivityFetcher(cache_basedir=cache_basedir, client=client)
        athlete_id = 123
        object_id = 456
        object_json = {"id": object_id, "name": "Test Activity"}
        cache_path = fetcher.cache_object_json(
            athlete_id=athlete_id, object_id=object_id, object_json=object_json
        )
        assert os.path.exists(cache_path)
        with open(cache_path, "r") as f:
            cached_data = json.load(f)
        assert cached_data == object_json

    def test_get_cached_object_json(self, cache_basedir, client):
        fetcher = CachingActivityFetcher(cache_basedir=cache_basedir, client=client)
        athlete_id = 123
        object_id = 456
        object_json = {"id": object_id, "name": "Test Activity"}
        fetcher.cache_object_json(
            athlete_id=athlete_id, object_id=object_id, object_json=object_json
        )
        cached_data = fetcher.get_cached_object_json(
            athlete_id=athlete_id, object_id=object_id
        )
        assert cached_data == object_json

    @patch.object(CachingActivityFetcher, "download_object_json")
    def test_retrieve_object_json(self, mock_download, cache_basedir, client):
        fetcher = CachingActivityFetcher(cache_basedir=cache_basedir, client=client)
        athlete_id = 123
        object_id = 456
        object_json = {"id": object_id, "name": "Test Activity"}
        mock_download.return_value = object_json

        # Test cache miss
        retrieved_data = fetcher.retrieve_object_json(
            athlete_id=athlete_id, object_id=object_id, use_cache=True, only_cache=False
        )
        assert retrieved_data == object_json
        mock_download.assert_called_once_with(
            athlete_id=athlete_id, object_id=object_id
        )

        # Test cache hit
        retrieved_data = fetcher.retrieve_object_json(
            athlete_id=athlete_id, object_id=object_id, use_cache=True, only_cache=False
        )
        assert retrieved_data == object_json
        mock_download.assert_called_once()  # Ensure download is not called again


class TestCachingActivityFetcher:
    @patch.object(CachingActivityFetcher, "download_object_json")
    def test_fetch(self, mock_download, cache_basedir, client):
        fetcher = CachingActivityFetcher(cache_basedir=cache_basedir, client=client)
        athlete_id = 123
        object_id = 456
        activity_json = {"id": object_id, "name": "Test Activity"}
        mock_download.return_value = activity_json

        # Test fetch with cache miss
        fetched_activity = fetcher.fetch(
            athlete_id=athlete_id, object_id=object_id, use_cache=True, only_cache=False
        )
        assert fetched_activity.id == object_id
        assert fetched_activity.name == "Test Activity"

        # Test fetch with cache hit
        fetched_activity = fetcher.fetch(
            athlete_id=athlete_id, object_id=object_id, use_cache=True, only_cache=False
        )
        assert fetched_activity.id == object_id
        assert fetched_activity.name == "Test Activity"
        mock_download.assert_called_once()  # Ensure download is not called again


class TestCachingStreamFetcher:
    @patch.object(CachingStreamFetcher, "download_object_json")
    def test_fetch(self, mock_download, cache_basedir, client):
        fetcher = CachingStreamFetcher(cache_basedir=cache_basedir, client=client)
        athlete_id = 123
        object_id = 456
        streams_json = [{"type": "latlng", "data": [[1.0, 2.0], [3.0, 4.0]]}]
        mock_download.return_value = streams_json

        # Test fetch with cache miss
        fetched_streams = fetcher.fetch(
            athlete_id=athlete_id, object_id=object_id, use_cache=True, only_cache=False
        )
        assert len(fetched_streams) == 1
        assert fetched_streams[0].type == "latlng"
        assert fetched_streams[0].data == [[1.0, 2.0], [3.0, 4.0]]

        # Test fetch with cache hit
        fetched_streams = fetcher.fetch(
            athlete_id=athlete_id, object_id=object_id, use_cache=True, only_cache=False
        )
        assert len(fetched_streams) == 1
        assert fetched_streams[0].type == "latlng"
        assert fetched_streams[0].data == [[1.0, 2.0], [3.0, 4.0]]
        mock_download.assert_called_once()  # Ensure download is not called again
