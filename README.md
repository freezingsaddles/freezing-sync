# Freezing Saddles Sync

This component is part of the [Freezing Saddles](http://freezingsaddles.com) project. Its purpose is to:

1. Receive workflow messages published from [freezing-nq](https://github.com/freezingsaddles/freezing-nq) and perform Strava API calls to retrieve activities/streams/etc.
2. Perform periodic (cron-like) double checks to make sure that we haven't missed any activity updates/deletes.
3. Perform periodic updates for non-Strava data (e.g. weather data).

## Development Setup

This project supports local development both with Docker and by running directly on the host.

To get started, you should clone the project and install the dependencies:

```bash
shell$ git clone https://github.com/freezingsaddles/freezing-sync
shell$ cd freezing-web
shell$ python3 -m venv env
shell$ source env/bin/activate
(env) shell$ pip install -e '.[dev]'
``````

### Deploying With Docker

See [freezing-compose](https://github.com/freezingsaddles/freezing-compose) for guide to deploying this in production along
with the related containers.

This component is designed to run as a container and should be configured with environment variables for:

- `BEANSTALKD_HOST`: The hostname (probably a container link) to a beanstalkd server.
- `BEANSTALKD_PORT`: The port for beanstalkd server (default 11300)
- `SQLALCHEMY_URL`: The URL to the database.
- `STRAVA_CLIENT_ID`: The ID of the Strava application.
- `STRAVA_CLIENT_SECRET`: Secret key for the app (available from App settings page in Strava)
- `VISUAL_CROSSING_API_KEY`: The key to your visualcrossing.com development account.
- `VISUAL_CROSSING_CACHE_DIR`: The directory for visualcrossing.com cache files
- `TEAMS`: A comma-separated list of team (Strava club) IDs for the competition. = env('TEAMS', cast=list, subcast=int, default=[])
- `OBSERVER_TEAMS`: Comma-separated list of any teams that are just observing, not playing (they can get their overall stats included, but won't be part of leaderboards)
- `START_DATE`: The beginning of the competition.
- `END_DATE`: The end of the competition.
- `UPLOAD_GRACE_PERIOD`: How long (days) can people upload rides after competition>
- `EXCLUDE_KEYWORDS`: Any keywords to match on to exclude rides (default: "#NoBAFS"). Note: these are not case-sensitive.

### Running Locally

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
- `VISUAL_CROSSING_CACHE_DIR`: Similarly, where should weather files be stored?

### Coding standards

The `freezing-sync` code is intended to be [PEP-8](https://www.python.org/dev/peps/pep-0008/) compliant. Code formatting is done with [black](https://black.readthedocs.io/en/stable/), [isort](https://pycqa.github.io/isort/) and [djlint](https://www.djlint.com/) and can be linted with [flake8](http://flake8.pycqa.org/en/latest/). See the [pyproject.toml](pyproject.toml) file and install the dev dependencies to get these tools.

This project also has _optional_ support for [pre-commit](https://pre-commit.org) to run these checks automatically before you commit. To install pre-commit, install the `dev` dependencies and then run `pre-commit install` in the root of the repository.

## Legal

This software is a an [Apache 2.0 Licensed](LICENSE), community-driven effort, and as such the contributions are owned by the individual contributors:

- Copyright 2018 Hans Lellelid
- Copyright 2020 Richard Bullington-McGuire
- Copyright 2020 Merlin Hughes
