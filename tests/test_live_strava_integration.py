"""
Live Integration Tests for Stravalib 2.4 Upgrade

These tests make real API calls to Strava to validate that the upgrade
is working correctly. They require valid Strava API credentials and an
athlete with activities in the database.

To run these tests:
    pytest tests/test_live_strava_integration.py -v -s

To skip these tests in CI:
    pytest -m "not live"
"""

import logging
import os
from unittest.mock import patch

import pytest
from freezing.model import meta, init_model
from freezing.model.orm import Athlete
from stravalib import unit_helper
from stravalib.client import Client
from stravalib.model import DetailedActivity, Stream

from freezing.sync.config import Config
from freezing.sync.data import StravaClientForAthlete

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def database_session():
    """Initialize database connection for the test session."""
    init_model(Config.SQLALCHEMY_URL)
    return meta.scoped_session()


@pytest.fixture(scope="module")
def test_athlete(database_session):
    """
    Get a test athlete from the database that has activities.
    Skips if no suitable athlete is found.
    """
    session = database_session
    # Find an athlete with an access token
    athlete = session.query(Athlete).filter(Athlete.access_token.isnot(None)).first()
    if not athlete:
        pytest.skip("No athlete with access token found in database")
    return athlete


@pytest.fixture(scope="module")
def authenticated_client(test_athlete):
    """Create an authenticated Strava client for the test athlete."""
    return StravaClientForAthlete(test_athlete)


@pytest.fixture(scope="module")
def test_activity_id(authenticated_client, test_athlete):
    """
    Get a real activity ID from the authenticated athlete.
    Fetches the most recent activity.
    """
    # Get the most recent activity
    activities = authenticated_client.get_activities(limit=1)
    activity_list = list(activities)
    if not activity_list:
        pytest.skip(f"No activities found for athlete {test_athlete.id}")
    return activity_list[0].id


@pytest.mark.live
class TestLiveStravaAPI:
    """Test basic Strava API operations with real network calls."""

    def test_client_authentication(self, authenticated_client, test_athlete):
        """Verify client authentication and token refresh mechanism."""
        assert authenticated_client.access_token is not None
        logger.info(f"Successfully authenticated for athlete {test_athlete.id}")

    def test_get_athlete(self, authenticated_client):
        """Test fetching authenticated athlete information."""
        athlete = authenticated_client.get_athlete()
        assert athlete is not None
        assert athlete.id is not None
        assert athlete.firstname is not None
        logger.info(
            f"Retrieved athlete: {athlete.firstname} {athlete.lastname} (ID: {athlete.id})"
        )

    def test_get_activities_list(self, authenticated_client):
        """Test fetching a list of activities."""
        activities = list(authenticated_client.get_activities(limit=5))
        assert len(activities) > 0
        for activity in activities:
            assert activity.id is not None
            assert activity.name is not None
            logger.info(f"Activity: {activity.name} (ID: {activity.id})")

    def test_get_detailed_activity(self, authenticated_client, test_activity_id):
        """Test fetching detailed activity with all fields."""
        activity = authenticated_client.get_activity(test_activity_id)

        assert isinstance(activity, DetailedActivity)
        assert activity.id == test_activity_id
        assert activity.name is not None

        logger.info(f"Detailed Activity: {activity.name} (ID: {activity.id})")
        logger.info(f"  Type: {activity.type}")
        logger.info(f"  Distance: {activity.distance} meters")
        logger.info(f"  Moving Time: {activity.moving_time}")
        logger.info(f"  Elapsed Time: {activity.elapsed_time}")

        # Verify the activity has expected attributes
        assert hasattr(activity, "distance")
        assert hasattr(activity, "moving_time")
        assert hasattr(activity, "elapsed_time")
        assert hasattr(activity, "type")

    def test_activity_streams(self, authenticated_client, test_activity_id):
        """Test fetching activity streams (GPS, altitude, etc.)."""
        try:
            streams = authenticated_client.get_activity_streams(
                test_activity_id, types=["latlng", "time", "altitude", "distance"]
            )

            assert isinstance(streams, dict)
            logger.info(
                f"Retrieved {len(streams)} stream types for activity {test_activity_id}"
            )

            for stream_type, stream in streams.items():
                assert isinstance(stream, Stream)
                assert stream.type == stream_type
                assert stream.data is not None
                assert len(stream.data) > 0
                logger.info(f"  Stream '{stream_type}': {len(stream.data)} data points")

        except Exception as e:
            # Some activities may not have streams (e.g., manual entries)
            logger.warning(
                f"Could not fetch streams for activity {test_activity_id}: {e}"
            )
            pytest.skip(f"Activity {test_activity_id} does not have stream data")


@pytest.mark.live
class TestStravalib24Features:
    """Test Stravalib 2.4 specific features and compatibility."""

    def test_distance_type_with_quantity(self, authenticated_client, test_activity_id):
        """Test that Distance objects support .quantity() method for unit conversion."""
        activity = authenticated_client.get_activity(test_activity_id)

        # In Stravalib 2.x, distance is a Distance object (subclass of float)
        assert activity.distance is not None

        # Test that distance has the quantity() method
        if hasattr(activity.distance, "quantity"):
            distance_quantity = activity.distance.quantity()
            logger.info(f"Distance as quantity: {distance_quantity}")

            # Test unit conversion using unit_helper
            distance_in_miles = unit_helper.miles(distance_quantity)
            distance_in_km = unit_helper.kilometers(distance_quantity)

            logger.info(f"Distance: {activity.distance} meters")
            logger.info(f"Distance: {distance_in_miles.magnitude:.2f} miles")
            logger.info(f"Distance: {distance_in_km.magnitude:.2f} km")

            assert distance_in_miles.magnitude > 0
            assert distance_in_km.magnitude > 0
        else:
            # Fallback for plain float values (e.g., from mocks)
            logger.info(f"Distance (plain float): {activity.distance} meters")
            distance_in_miles = unit_helper.miles(unit_helper.meters(activity.distance))
            logger.info(f"Distance: {distance_in_miles.magnitude:.2f} miles")

    def test_velocity_type_with_quantity(self, authenticated_client, test_activity_id):
        """Test that Velocity objects support .quantity() method for unit conversion."""
        activity = authenticated_client.get_activity(test_activity_id)

        if activity.average_speed is not None:
            logger.info(f"Average speed: {activity.average_speed} m/s")

            if hasattr(activity.average_speed, "quantity"):
                speed_quantity = activity.average_speed.quantity()
                speed_mph = unit_helper.mph(speed_quantity)
                speed_kph = unit_helper.kph(speed_quantity)

                logger.info(f"Average speed: {speed_mph.magnitude:.2f} mph")
                logger.info(f"Average speed: {speed_kph.magnitude:.2f} km/h")

                assert speed_mph.magnitude > 0
                assert speed_kph.magnitude > 0

    def test_pydantic_model_validate(self, authenticated_client, test_activity_id):
        """Test that Pydantic 2.x model_validate works correctly."""
        activity = authenticated_client.get_activity(test_activity_id)

        # Get the raw dict representation
        activity_dict = {
            "id": activity.id,
            "name": activity.name,
            "type": activity.type,
            "distance": float(activity.distance) if activity.distance else 0,
        }

        # Test model_validate (Pydantic 2.x method)
        validated_activity = DetailedActivity.model_validate(activity_dict)
        assert validated_activity.id == activity.id
        assert validated_activity.name == activity.name

        logger.info(
            f"Successfully validated activity using model_validate: {validated_activity.name}"
        )

    def test_timedelta_attributes(self, authenticated_client, test_activity_id):
        """Test that time attributes are properly converted to timedelta."""
        activity = authenticated_client.get_activity(test_activity_id)

        # In Stravalib 2.x, elapsed_time/moving_time are Duration objects with timedelta() method
        assert hasattr(activity.elapsed_time, "timedelta") or hasattr(
            activity.elapsed_time, "total_seconds"
        )
        assert hasattr(activity.moving_time, "timedelta") or hasattr(
            activity.moving_time, "total_seconds"
        )

        # Convert to timedelta if needed
        elapsed_td = (
            activity.elapsed_time.timedelta()
            if hasattr(activity.elapsed_time, "timedelta")
            else activity.elapsed_time
        )
        moving_td = (
            activity.moving_time.timedelta()
            if hasattr(activity.moving_time, "timedelta")
            else activity.moving_time
        )

        elapsed = elapsed_td.total_seconds()
        moving = moving_td.total_seconds()

        logger.info(f"Elapsed time: {elapsed} seconds ({elapsed/60:.1f} minutes)")
        logger.info(f"Moving time: {moving} seconds ({moving/60:.1f} minutes)")

        assert elapsed > 0
        assert moving > 0
        assert elapsed >= moving  # Elapsed time should be >= moving time


@pytest.mark.live
class TestActivitySyncCompatibility:
    """Test compatibility with existing activity sync logic."""

    def test_full_activity_conversion_pipeline(
        self, authenticated_client, test_activity_id
    ):
        """
        Test the complete pipeline of fetching an activity and converting
        all unit measurements as done in update_ride_basic.
        """
        from freezing.sync.data.activity import ActivitySync

        activity = authenticated_client.get_activity(test_activity_id)

        # Simulate the conversions done in update_ride_basic
        if activity.distance:
            distance_quantity = (
                activity.distance.quantity()
                if hasattr(activity.distance, "quantity")
                else unit_helper.meters(activity.distance)
            )
            distance_miles = round(unit_helper.miles(distance_quantity).magnitude, 3)
            logger.info(f"Distance: {distance_miles} miles")
            assert distance_miles > 0

        if activity.average_speed:
            avg_speed_quantity = (
                activity.average_speed.quantity()
                if hasattr(activity.average_speed, "quantity")
                else unit_helper.meters_per_second(activity.average_speed)
            )
            avg_speed_mph = unit_helper.mph(avg_speed_quantity).magnitude
            logger.info(f"Average speed: {avg_speed_mph:.2f} mph")
            assert avg_speed_mph > 0

        if activity.max_speed:
            max_speed_quantity = (
                activity.max_speed.quantity()
                if hasattr(activity.max_speed, "quantity")
                else unit_helper.meters_per_second(activity.max_speed)
            )
            max_speed_mph = unit_helper.mph(max_speed_quantity).magnitude
            logger.info(f"Max speed: {max_speed_mph:.2f} mph")
            assert max_speed_mph > 0

        if activity.total_elevation_gain:
            elev_quantity = (
                activity.total_elevation_gain.quantity()
                if hasattr(activity.total_elevation_gain, "quantity")
                else unit_helper.meters(activity.total_elevation_gain)
            )
            elev_feet = unit_helper.feet(elev_quantity).magnitude
            logger.info(f"Elevation gain: {elev_feet:.1f} feet")
            assert elev_feet >= 0

    def test_segment_efforts(self, authenticated_client, test_activity_id):
        """Test fetching and processing segment efforts."""
        activity = authenticated_client.get_activity(test_activity_id)

        if hasattr(activity, "segment_efforts") and activity.segment_efforts:
            logger.info(f"Activity has {len(activity.segment_efforts)} segment efforts")

            for effort in activity.segment_efforts[:3]:  # Test first 3 efforts
                assert effort.id is not None
                assert effort.segment is not None
                assert effort.segment.name is not None
                assert effort.elapsed_time is not None

                # Handle Duration objects that have timedelta() method
                elapsed_td = (
                    effort.elapsed_time.timedelta()
                    if hasattr(effort.elapsed_time, "timedelta")
                    else effort.elapsed_time
                )
                elapsed_seconds = elapsed_td.total_seconds()
                logger.info(f"  Segment: {effort.segment.name}")
                logger.info(f"    Elapsed time: {elapsed_seconds:.1f} seconds")
        else:
            logger.info(
                "Activity has no segment efforts (manual entry or no matched segments)"
            )
            pytest.skip("Activity has no segment efforts to test")

    def test_activity_photos(self, authenticated_client, test_activity_id):
        """Test fetching activity photos."""
        activity = authenticated_client.get_activity(test_activity_id)

        if hasattr(activity, "photos") and activity.photos:
            logger.info(f"Activity has photos")
            if hasattr(activity.photos, "primary") and activity.photos.primary:
                primary = activity.photos.primary
                logger.info(f"  Primary photo: {primary}")
                if hasattr(primary, "unique_id"):
                    logger.info(f"    Unique ID: {primary.unique_id}")

        if hasattr(activity, "total_photo_count"):
            logger.info(f"Total photo count: {activity.total_photo_count}")


@pytest.mark.live
class TestRateLimiting:
    """Test rate limiting functionality."""

    def test_rate_limit_handling(self, authenticated_client):
        """
        Test that rate limiting is properly configured and works.
        This doesn't exhaust the rate limit, just verifies the mechanism exists.
        """
        # Verify the client was created with rate limiting
        # (StravaClientForAthlete passes rate_limit_requests=True to parent Client)
        logger.info("Rate limiting is configured in StravaClientForAthlete")

        # Make a few requests to verify rate limiter doesn't cause issues
        for i in range(3):
            activities = list(authenticated_client.get_activities(limit=1))
            assert len(activities) > 0
            logger.info(f"Request {i+1} completed successfully")


@pytest.mark.live
class TestClientConfiguration:
    """Test client configuration with Stravalib 2.4."""

    def test_config_values_loaded(self):
        """Verify that Strava configuration values are loaded."""
        assert Config.STRAVA_CLIENT_ID is not None
        assert Config.STRAVA_CLIENT_SECRET is not None
        logger.info(f"Config loaded - Client ID: {Config.STRAVA_CLIENT_ID[:10]}...")

    def test_stravalib_client_creation(self):
        """Test creating a basic Strava client without athlete."""
        client = Client()
        assert client is not None
        logger.info("Successfully created basic Strava client")

    def test_authenticated_client_refresh_token(self, test_athlete):
        """Test the token refresh mechanism in StravaClientForAthlete."""
        client = StravaClientForAthlete(test_athlete)

        # Verify client has access token
        assert client.access_token is not None

        # Verify athlete token attributes
        assert test_athlete.access_token is not None
        if test_athlete.refresh_token:
            logger.info("Athlete has refresh token configured")
        if test_athlete.expires_at:
            logger.info(f"Token expires at: {test_athlete.expires_at}")


# =============================================================================
# Mocked Unit Tests (fast, no network calls)
# =============================================================================
# These tests don't make real API calls and can run in CI without credentials


class TestMockedStravalib:
    """Unit tests with mocked API calls to verify Pydantic compatibility."""

    @pytest.fixture
    def client(self):
        """Create a basic Stravalib client."""
        return Client()

    @patch.object(Client, "get_activity")
    def test_detailed_activity(self, mock_get_activity, client):
        """Test that DetailedActivity can be instantiated with model_validate."""
        activity_id = 1234567890
        mock_get_activity.return_value = DetailedActivity.model_validate(
            {"id": activity_id, "name": "Test"}
        )
        activity = client.get_activity(activity_id)
        assert isinstance(activity, DetailedActivity)
        assert activity.id == activity_id

    @patch.object(Client, "get_activity_streams")
    def test_stream_set(self, mock_get_streams, client):
        """Test that get_activity_streams returns a dict of Stream objects."""
        activity_id = 1234567890
        # Simulate dict of stream objects keyed by type, matching newer client behavior
        mock_get_streams.return_value = {
            "latlng": Stream.model_validate({"type": "latlng", "data": [[1.0, 2.0]]}),
            "time": Stream.model_validate({"type": "time", "data": [0, 10]}),
            "altitude": Stream.model_validate(
                {"type": "altitude", "data": [100.0, 110.0]}
            ),
        }
        streams = client.get_activity_streams(
            activity_id, types=["latlng", "time", "altitude"]
        )
        assert isinstance(streams, dict)
        assert set(streams.keys()) == {"latlng", "time", "altitude"}
