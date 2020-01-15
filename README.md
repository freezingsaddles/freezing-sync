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
- `DARK_SKY_API_KEY`: The key to your darksky.net development account.
- `DARK_SKY_CACHE_DIR`: The directory for darksky.net cache files
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

You can run individual sync commands too:
```bash
APP_SETTINGS=local.cfg python -m freezing.sync.cli.sync_weather --debug --limit 1
```

There are a few additional settings you may need (i.e. not to be default) when not running in Docker:
- `STRAVA_ACTIVITY_CACHE_DIR`: Where to put cached activities (absolute path is a good idea).
- `DARK_SKY_CACHE_DIR`: Similarly, where should weather files be stored?
`

## Testing the dark sky API

If you, like I, don't know what you're doing, you can experiment with the dark sky API in the repl:

```bash
# pip install rwt
# python -m rwt -q darksky_weather
>>> from darksky.api import DarkSky
>>> from darksky.types import languages, units, weather
>>> from datetime import datetime
>>> darksky = DarkSky('YOUR_API_KEY')
>>> hist = darksky.get_time_machine_forecast(time = datetime(2019, 2, 18), latitude = 37.6, longitude = -77.5, exclude=[weather.MINUTELY, weather.ALERTS])
>>> [ x.temperature for x in hist.hourly.data ]
[37.5, 37.17, 37.38, 37.82, 38.28, 38.71, 39.43, 40.04, 41.57, 44.51, 49.19, 52.36, 54.33, 56.05, 56.36, 55.7, 54.18, 51.96, 48.39, 45.94, 44.08, 42.6, 41.32, 40.13]
```

