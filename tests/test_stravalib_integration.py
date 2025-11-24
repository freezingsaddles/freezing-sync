import pytest
from unittest.mock import patch
from stravalib.client import Client
from stravalib.model import DetailedActivity, Stream


@pytest.fixture
def client():
    return Client()


@patch.object(Client, "get_activity")
def test_detailed_activity(mock_get_activity, client):
    activity_id = 1234567890
    mock_get_activity.return_value = DetailedActivity.model_validate(
        {"id": activity_id, "name": "Test"}
    )
    activity = client.get_activity(activity_id)
    assert isinstance(activity, DetailedActivity)
    assert activity.id == activity_id


@patch.object(Client, "get_activity_streams")
def test_stream_set(mock_get_streams, client):
    activity_id = 1234567890
    # Simulate dict of stream objects keyed by type, matching newer client behavior
    mock_get_streams.return_value = {
        "latlng": Stream.model_validate({"type": "latlng", "data": [[1.0, 2.0]]}),
        "time": Stream.model_validate({"type": "time", "data": [0, 10]}),
        "altitude": Stream.model_validate({"type": "altitude", "data": [100.0, 110.0]}),
    }
    streams = client.get_activity_streams(
        activity_id, types=["latlng", "time", "altitude"]
    )
    assert isinstance(streams, dict)
    assert set(streams.keys()) == {"latlng", "time", "altitude"}
