import pytest
from stravalib.client import Client
from stravalib.model import DetailedActivity, StreamSet

@pytest.fixture
def client():
    return Client()

def test_detailed_activity(client):
    activity_id = 1234567890
    activity = client.get_activity(activity_id)
    assert isinstance(activity, DetailedActivity)
    assert activity.id == activity_id

def test_stream_set(client):
    activity_id = 1234567890
    streams = client.get_activity_streams(activity_id, types=['latlng', 'time', 'altitude'])
    assert isinstance(streams, StreamSet)
    assert 'latlng' in streams
    assert 'time' in streams
    assert 'altitude' in streams
