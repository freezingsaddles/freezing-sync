# Freezing Saddles Sync

This component is part of the [Freezing Saddles](http://freezingsaddles.com) project.  Its purpose is to
1. receive workflow messages published from [freezing-nq](https://github.com/freezingsaddles/freezing-nq) and perform Strava API calls to retrieve activities/streams/etc.
2. Perform periodic (cron-like) double checks to make sure that we haven't missed any activity updates/deletes.
3. Perform periodic updates for non-Strava data (e.g. weather data).

## Deploying With Docker

See [freezing-compose](https://github.com/freezingsaddles/freezing-compose) for guide to deploying this in production along
with the related containers.

This component is designed to run as a container and should be configured with environment variables for:
- `BEANSTALKD_HOST`: The hostname (probably a container link) to a beanstalkd server.
- `BEANSTALKD_PORT`: The port for beanstalkd server (default 11300)
- `SQLALCHEMY_URL`: The URL to the database.
- `STRAVA_CLIENT_ID`: The ID of the Strava application.
- `STRAVA_CLIENT_SECRET`: Secret key for the app (available from App settings page in Strava)
- `WUNDERGROUND_API_KEY`: The key to your wunderground.com development account.
- `WUNDERGROUND_CACHE_DIR`: The directory for wunderground.com cache files
- `TEAMS`: A comma-separated list of team (Strava club) IDs for the competition. = env('TEAMS', cast=list, subcast=int, default=[])
- `OBSERVER_TEAMS`: Comma-separated list of any teams that are just observing, not playing (they can get their overall stats included, but won't be part of leaderboards)
- `START_DATE`: The beginning of the competition.
- `END_DATE`: The end of the competition.
- `UPLOAD_GRACE_PERIOD`: How long (days) can people upload rides after competition>
- `EXCLUDE_KEYWORDS`: Any keywords to match on to exclude rides (default: "#NoBAFS"). Note: these are not case-sensitive.

## Running Locally

If you are running this component locally for development/debugging, you may set these values in a configuration file, and specify the path to this file with the `APP_SETTINGS` environment variable.  For example:
```bash
APP_SETTINGS=local.cfg freezing-sync
```

There are a few additional settings you may need (i.e. not to be default) when not running in Docker:
- `STRAVA_ACTIVITY_CACHE_DIR`: Where to put cached activities (absolute path is a good idea).
- `WUNDERGROUND_CACHE_DIR`: Similarly, where should weather files be stored?
`
