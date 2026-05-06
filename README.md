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
shell$ cd freezing-sync
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

#### Example local.cfg

Here is a minimal `local.cfg` for local development. The database is provided by
[freezing-web](https://github.com/freezingsaddles/freezing-web)'s Docker Compose setup —
start it with `docker-compose up -d freezing-db` from the `freezing-web` directory before
running any sync commands.

````ini
SQLALCHEMY_URL = mysql+pymysql://freezing:zeer0@127.0.0.1:3306/freezing
STRAVA_CLIENT_ID = 12345
STRAVA_CLIENT_SECRET = your_strava_client_secret
VISUAL_CROSSING_API_KEY = your_visual_crossing_api_key
STRAVA_ACTIVITY_CACHE_DIR = data/cache/activities
VISUAL_CROSSING_CACHE_DIR = data/cache/weather
MAIN_TEAM = 12345
TEAMS = 12345,67890
START_DATE = 2025-01-01
END_DATE = 2025-02-28
UPLOAD_GRACE_PERIOD = 2
DEBUG = false
```

#### One-shot CLI commands

For local development, you can run individual sync operations without starting the full daemon
and without Beanstalkd running. The two most useful are:

```bash
# Sync athlete records (names, team membership) from Strava
APP_SETTINGS=local.cfg freezing-sync-athletes

# Sync ride activities for all athletes
APP_SETTINGS=local.cfg freezing-sync-activities

# Sync weather data for all rides (requires VISUAL_CROSSING_API_KEY)
APP_SETTINGS=local.cfg freezing-sync-weather
```

> **Note:** The free tier of Visual Crossing allows 1000 records per day. Weather results are
> cached locally (see `VISUAL_CROSSING_CACHE_DIR`), so re-running the command on subsequent days
> will make incremental progress without re-fetching already-cached dates.

These commands run, do their work, and exit. The main `freezing-sync` entry point is a
long-running daemon that requires Beanstalkd; use these CLI commands instead for local testing.

#### Getting OAuth tokens for local testing

`freezing-sync` requires real Strava OAuth tokens to call the Strava API. These tokens are stored
in the `athletes` table by [freezing-web](https://github.com/freezingsaddles/freezing-web) when
an athlete completes the Strava OAuth flow.

A freshly initialized local database has no athletes and no tokens, so `freezing-sync-athletes`
and `freezing-sync-activities` will have nothing to sync. The recommended approach for local
development is to restore a production database dump — see the "On dumping and restoring the
database" section in the freezing-web README for instructions.

**Strava club membership and team assignment:** `freezing-sync` assigns athletes to teams based
on which Strava clubs they belong to, matched against the club IDs in `MAIN_TEAM` and `TEAMS` in
your `local.cfg`. The sync will run without club membership, but athletes will have no team
assigned. For realistic local data, consider joining last year's competition clubs on Strava —
the club IDs are visible in the URL at `https://www.strava.com/clubs/CLUB_ID`.

**Manual token bootstrap procedure** (if you don't have a DB dump):

1. Visit this URL in your browser (substituting your `STRAVA_CLIENT_ID`):

   ```
   https://www.strava.com/oauth/authorize?client_id=CLIENT_ID&redirect_uri=http://127.0.0.1:5000/authorization&response_type=code&scope=read,activity:read_all,profile:read_all,read_all
   ```

   After authorizing, Strava will redirect to your local server. Copy the `code` value from the
   redirect URL query string.

2. Exchange the code for tokens:

   ```bash
   curl -X POST https://www.strava.com/oauth/token \
     -d client_id=CLIENT_ID \
     -d client_secret=CLIENT_SECRET \
     -d code=AUTH_CODE \
     -d grant_type=authorization_code
   ```

   The response will contain `access_token`, `refresh_token`, `expires_at`, and the athlete's
   `id`.

3. Insert the tokens directly into the database:

   ```sql
   INSERT INTO athletes (id, name, display_name, access_token, refresh_token, expires_at)
   VALUES (ATHLETE_ID, 'Your Name', 'Your Name', 'ACCESS_TOKEN', 'REFRESH_TOKEN', EXPIRES_AT)
   ON DUPLICATE KEY UPDATE
     access_token = VALUES(access_token),
     refresh_token = VALUES(refresh_token),
     expires_at = VALUES(expires_at);
   ```

See [freezing-web#620](https://github.com/freezingsaddles/freezing-web/issues/620) and
[freezing-sync#24](https://github.com/freezingsaddles/freezing-sync/issues/24) for more context
on this local development limitation.

### Running Unit Tests

To run the unit tests, you can use `pytest`. Make sure you have all the dependencies installed, including the ones in `requirements-test.txt`. You can run the tests with the following command:

```bash
pytest
```

### Coding standards

The `freezing-sync` code is intended to be [PEP-8](https://www.python.org/dev/peps/pep-0008/) compliant. Code formatting is done with [black](https://black.readthedocs.io/en/stable/), [isort](https://pycqa.github.io/isort/) and [djlint](https://www.djlint.com/) and can be linted with [flake8](http://flake8.pycqa.org/en/latest/). See the [pyproject.toml](pyproject.toml) file and install the dev dependencies to get these tools.

This project also has _optional_ support for [pre-commit](https://pre-commit.org) to run these checks automatically before you commit. To install pre-commit, install the `dev` dependencies and then run `pre-commit install` in the root of the repository.

## Legal

This software is a an [Apache 2.0 Licensed](LICENSE), community-driven effort, and as such the contributions are owned by the individual contributors:

- Copyright 2018 Hans Lellelid
- Copyright 2020 Richard Bullington-McGuire
- Copyright 2020 Merlin Hughes
