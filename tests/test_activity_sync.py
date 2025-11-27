from datetime import datetime, timedelta
from types import SimpleNamespace
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
    """Return a lightweight DetailedActivity-like object with required attributes."""
    from stravalib.model import Distance, Velocity

    class DummyActivity(SimpleNamespace):
        pass

    activity = DummyActivity()
    activity.id = 123
    activity.name = "Test Activity"
    activity.private = False
    activity.photo_count = 1
    activity.total_photo_count = 1
    activity.start_date_local = datetime.now()
    activity.distance = Distance(1000.0)
    activity.average_speed = Velocity(10.0)
    activity.max_speed = Velocity(20.0)
    activity.elapsed_time = timedelta(hours=1)
    activity.moving_time = timedelta(hours=1)
    activity.location_city = "Test City"
    activity.location_state = "Test State"
    activity.commute = False
    activity.trainer = False
    activity.manual = False
    activity.visibility = "everyone"
    activity.total_elevation_gain = Distance(100.0)
    activity.timezone = "UTC"
    # Photos container with primary attribute
    activity.photos = SimpleNamespace(primary=None)
    activity.segment_efforts = []
    return activity


@pytest.fixture
def ride():
    class DummyRide(SimpleNamespace):
        pass

    r = DummyRide()
    r.id = 999
    r.resync_count = 0
    r.photos_fetched = None
    r.athlete = SimpleNamespace(name="Test Athlete")
    return r


def test_update_ride_basic(activity_sync, detailed_activity, ride):
    activity_sync.update_ride_basic(detailed_activity, ride)
    assert ride.name == detailed_activity.name
    assert ride.private == detailed_activity.private
    assert ride.start_date == detailed_activity.start_date_local
    # Use approximate comparisons for float values from unit conversions
    assert ride.distance == pytest.approx(0.621, rel=1e-3)  # 1000m to miles
    assert ride.average_speed == pytest.approx(22.369, rel=1e-3)  # 10 m/s to mph
    assert ride.maximum_speed == pytest.approx(44.738, rel=1e-3)  # 20 m/s to mph
    assert ride.elapsed_time == detailed_activity.elapsed_time.total_seconds()
    assert ride.moving_time == detailed_activity.moving_time.total_seconds()
    assert ride.location == "Test City, Test State"
    assert ride.commute == detailed_activity.commute
    assert ride.trainer == detailed_activity.trainer
    assert ride.manual == detailed_activity.manual
    assert ride.visibility == detailed_activity.visibility
    assert ride.elevation_gain == pytest.approx(328.084, rel=1e-3)  # 100m to feet
    assert ride.timezone == detailed_activity.timezone


def test_write_ride_efforts(activity_sync, detailed_activity, ride):
    session = MagicMock()
    detailed_activity.segment_efforts = [
        SimpleNamespace(
            id=1,
            elapsed_time=timedelta(seconds=300),
            segment=SimpleNamespace(name="Segment 1", id=1),
            achievements=[],
        ),
        SimpleNamespace(
            id=2,
            elapsed_time=timedelta(seconds=600),
            segment=SimpleNamespace(name="Segment 2", id=2),
            achievements=[],
        ),
    ]
    with patch("freezing.sync.data.activity.meta.scoped_session", return_value=session):
        activity_sync.write_ride_efforts(detailed_activity, ride)
        assert session.add.call_count == 2
        assert session.flush.call_count == 2


def test_write_ride_photo_primary(activity_sync, detailed_activity, ride):
    session = MagicMock()
    primary_photo = SimpleNamespace(
        source=1,
        unique_id="test_photo_123",
        urls={
            "100": "https://example.com/100.jpg",
            "600": "https://example.com/600.jpg",
        },
    )
    detailed_activity.photos.primary = primary_photo
    detailed_activity.total_photo_count = 1
    with patch("freezing.sync.data.activity.meta.scoped_session", return_value=session):
        activity_sync.write_ride_photo_primary(detailed_activity, ride)
        assert session.add.call_count == 1
        assert session.flush.call_count == 1


def test_update_ride_complete(activity_sync, detailed_activity, ride):
    session = MagicMock()
    detailed_activity.total_photo_count = 0
    with patch("freezing.sync.data.activity.meta.scoped_session", return_value=session):
        activity_sync.update_ride_complete(detailed_activity, ride)
        assert getattr(ride, "detail_fetched", False) is True
        assert ride.distance == pytest.approx(0.621, rel=1e-3)
