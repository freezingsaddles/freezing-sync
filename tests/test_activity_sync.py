from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from freezing.model.orm import Athlete, Ride, RideEffort, RidePhoto
from stravalib.model import ActivityPhotoPrimary, DetailedActivity

from freezing.sync.data.activity import ActivitySync
from freezing.sync.utils.cache import CachingActivityFetcher


@pytest.fixture
def activity_sync():
    return ActivitySync()


@pytest.fixture
def detailed_activity():
    activity = MagicMock(spec=DetailedActivity)
    activity.id = 123
    activity.name = "Test Activity"
    activity.private = False
    activity.photo_count = 1
    activity.start_date_local = datetime.now()
    activity.distance = MagicMock()
    activity.distance.num = 1000
    activity.average_speed = MagicMock()
    activity.average_speed.num = 10
    activity.max_speed = MagicMock()
    activity.max_speed.num = 20
    activity.elapsed_time = timedelta(hours=1)
    activity.moving_time = timedelta(hours=1)
    activity.location_city = "Test City"
    activity.location_state = "Test State"
    activity.commute = False
    activity.trainer = False
    activity.manual = False
    activity.total_elevation_gain = MagicMock()
    activity.total_elevation_gain.num = 100
    activity.timezone = "UTC"
    return activity


@pytest.fixture
def ride():
    return MagicMock(spec=Ride)


def test_update_ride_basic(activity_sync, detailed_activity, ride):
    activity_sync.update_ride_basic(detailed_activity, ride)
    assert ride.name == detailed_activity.name
    assert ride.private == detailed_activity.private
    assert ride.start_date == detailed_activity.start_date_local
    assert ride.distance == 0.621
    assert ride.average_speed == 22.3694
    assert ride.maximum_speed == 44.7388
    assert ride.elapsed_time == detailed_activity.elapsed_time.seconds
    assert ride.moving_time == detailed_activity.moving_time.seconds
    assert ride.location == "Test City, Test State"
    assert ride.commute == detailed_activity.commute
    assert ride.trainer == detailed_activity.trainer
    assert ride.manual == detailed_activity.manual
    assert ride.elevation_gain == 328.084
    assert ride.timezone == detailed_activity.timezone


def test_write_ride_efforts(activity_sync, detailed_activity, ride):
    session = MagicMock()
    detailed_activity.segment_efforts = [
        MagicMock(
            id=1,
            elapsed_time=timedelta(seconds=300),
            segment=MagicMock(name="Segment 1", id=1),
        ),
        MagicMock(
            id=2,
            elapsed_time=timedelta(seconds=600),
            segment=MagicMock(name="Segment 2", id=2),
        ),
    ]
    with patch("freezing.sync.data.activity.meta.scoped_session", return_value=session):
        activity_sync.write_ride_efforts(detailed_activity, ride)
        assert session.add.call_count == 2
        assert session.flush.call_count == 2


def test_write_ride_photo_primary(activity_sync, detailed_activity, ride):
    session = MagicMock()
    primary_photo = MagicMock(spec=ActivityPhotoPrimary)
    primary_photo.source = 1
    primary_photo.urls = {
        "100": "http://example.com/100.jpg",
        "600": "http://example.com/600.jpg",
    }
    detailed_activity.photos.primary = primary_photo
    with patch("freezing.sync.data.activity.meta.scoped_session", return_value=session):
        activity_sync.write_ride_photo_primary(detailed_activity, ride)
        assert session.add.call_count == 1
        assert session.flush.call_count == 1


def test_update_ride_complete(activity_sync, detailed_activity, ride):
    session = MagicMock()
    with patch("freezing.sync.data.activity.meta.scoped_session", return_value=session):
        activity_sync.update_ride_complete(detailed_activity, ride)
        assert ride.detail_fetched == True
        assert session.flush.call_count == 3
        assert session.commit.call_count == 1
