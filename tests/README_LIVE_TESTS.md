# Live Integration Tests (Stravalib 2.4)

Live tests in `test_live_strava_integration.py` call the real Strava API to validate the Stravalib 2.4 upgrade. They are optional and consume rate limits.

## Overview

### Basic API Operations

- Authentication and token refresh
- Athlete profile fetch
- Activity list and detailed activity fetch
- Activity streams (GPS, altitude, time)

### Stravalib 2.4 Features

- Distance / Velocity `.quantity()` access
- Unit conversions via `unit_helper`
- Pydantic 2.x `model_validate()` parsing
- Duration / timedelta handling

### Sync Compatibility

- Full conversion pipeline
- Segment efforts
- Activity photos

### Infrastructure

- Rate limiting behavior
- Config loading

## Prerequisites

### Database

One athlete row with valid `access_token` (or `refresh_token`) and at least one activity.

### Environment Variables

```bash
STRAVA_CLIENT_ID=your_client_id
STRAVA_CLIENT_SECRET=your_client_secret
SQLALCHEMY_URL=your_database_url
```

### Credentials

Tokens must be valid (not revoked or expired). Refresh tokens are used automatically.

## Running

### All Live Tests

```bash
pytest tests/test_live_strava_integration.py -v -s
```

### Single Class

```bash
pytest tests/test_live_strava_integration.py::TestLiveStravaAPI -v -s
```

### Single Test

```bash
pytest tests/test_live_strava_integration.py::TestLiveStravaAPI::test_get_detailed_activity -v -s
```

### Skip Live (CI)

```bash
pytest -m "not live"
```

### Only Live

```bash
pytest -m live -v -s
```

## Expected Output (Excerpt)

```text
tests/test_live_strava_integration.py::TestLiveStravaAPI::test_get_athlete PASSED
tests/test_live_strava_integration.py::TestLiveStravaAPI::test_get_detailed_activity PASSED
```

## Troubleshooting

### No Athlete

SKIPPED … No athlete with access token → Add athlete with valid token.

### No Activities Found

```text
SKIPPED [1] No activities found for athlete
```

Solution: The test athlete needs to have at least one activity. Either use a different athlete or create an activity.

### Authentication Errors

```text
stravalib.exc.AccessUnauthorized: Unauthorized
```

Solution:
- Verify `STRAVA_CLIENT_ID` and `STRAVA_CLIENT_SECRET` are correct
- Check that the athlete's access token is valid
- Ensure the token has not been revoked in Strava's settings

### Rate Limit Errors

```text
stravalib.exc.RateLimitExceeded
```

Solution: Wait for the rate limit window to reset (usually 15 minutes). The client automatically handles rate limiting, but if you've made many API calls recently, you may need to wait.

## Notes

⚠️ Real Strava rate limits: 100 / 15 min, 1000 / day.
⚠️ Not recommended for CI—exclude with `-m "not live"`.
✅ Read-only operations (safe to repeat).

## Coverage Summary

Integration tests complement unit tests by validating:

1. Real response parsing and models
2. Accurate unit conversions on live data
3. Token refresh flow
4. Stream and segment edge cases
5. Resilience to missing optional data

Together they provide confidence in the Stravalib 2.4 upgrade.# Live Integration Tests (Stravalib 2.4)

Live tests in `tests/test_live_strava_integration.py` exercise the real Strava API to validate the Stravalib 2.4 upgrade. They are optional and rate‑limited.

### TestLiveStravaAPI

Basic Strava API operations to verify connectivity and data retrieval.

- `test_client_authentication`: Verifies authentication works
- `test_get_athlete`: Fetches authenticated athlete info
- `test_get_activities_list`: Retrieves activity list
- `test_get_detailed_activity`: Fetches full activity details
- `test_activity_streams`: Tests stream data (GPS, altitude, etc.)

### TestStravalib24Features

Tests specific to Stravalib 2.4 compatibility.

- `test_distance_type_with_quantity`: Verifies `Distance.quantity()` method
- `test_velocity_type_with_quantity`: Verifies `Velocity.quantity()` method
- `test_pydantic_model_validate`: Tests Pydantic 2.x compatibility
- `test_timedelta_attributes`: Verifies time conversions

### TestActivitySyncCompatibility

Tests the complete activity sync pipeline.

- `test_full_activity_conversion_pipeline`: End-to-end unit conversions
- `test_segment_efforts`: Segment effort processing
- `test_activity_photos`: Photo metadata handling

### TestRateLimiting

Verifies rate limiting is properly configured.

### TestClientConfiguration

Tests configuration and client initialization.

## Expected Output

When tests run successfully, you'll see output similar to:

```text
tests/test_live_strava_integration.py::TestLiveStravaAPI::test_get_athlete PASSED
  Successfully authenticated for athlete 12345
  Retrieved athlete: John Doe (ID: 12345)

tests/test_live_strava_integration.py::TestLiveStravaAPI::test_get_detailed_activity PASSED
  Detailed Activity: Morning Ride (ID: 98765432)
    Type: Ride
    Distance: 25000.0 meters
    Moving Time: 0:45:30
    Elapsed Time: 0:50:15
```

## Important Notes

⚠️ These tests make real API calls and count against your Strava API rate limits (100 requests per 15 minutes, 1000 requests per day).

⚠️ Not suitable for CI unless you have a dedicated test athlete and can handle rate limiting. Use `-m "not live"` in CI pipelines.

✅ Best for local development and manual validation of the Stravalib upgrade.

✅ Safe to run repeatedly — tests are read-only and don't modify data.

## Test Coverage

These integration tests complement the existing unit tests by:

1. Validating real API responses match expected formats
2. Confirming unit conversions work with actual data
3. Verifying token refresh mechanisms work in practice
4. Testing rate limiting behavior
5. Ensuring Stravalib 2.4 breaking changes are properly handled

The combination of unit tests (mock-based) and integration tests (live API) provides comprehensive coverage of the Stravalib upgrade.
Solution: Wait for the rate limit window to reset (usually 15 minutes). The client automatically handles rate limiting, but if you've made many API calls recently, you may need to wait.
