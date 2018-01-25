import logging
from datetime import timedelta
from typing import List

from envparse import Env

import arrow

from freezing.model import init_model

env = Env(
    DEBUG=dict(cast=bool, default=False),

    SQLALCHEMY_URL=str,

    BEANSTALKD_HOST=dict(cast=str, default='beanstalkd.container'),
    BEANSTALKD_PORT=dict(cast=int, default=11300),

    STRAVA_CLIENT_ID=int,
    STRAVA_CLIENT_SECRET=str,
    STRAVA_ACTIVITY_CACHE_DIR=dict(cast=str, default='/data/cache/activities'),

    WUNDERGROUND_API_KEY=str,
    WUNDERGROUND_CACHE_DIR=dict(cast=str, default='/data/cache/weather'),

    TEAMS=dict(cast=list, subcast=int, default=[]),
    OBSERVER_TEAMS=dict(cast=list, subcast=int, default=[]),

    START_DATE=str,
    END_DATE=str,
    UPLOAD_GRACE_PERIOD_DAYS=dict(cast=int, default=1),

    EXCLUDE_KEYWORDS=dict(cast=list, subcast=str, default=['#NoBAFS']),
)


class Config:

    debug = env('DEBUG')  # type: bool
    sqlalchemy_url = env('SQLALCHEMY_URL')
    beanstalkd_host = env('BEANSTALKD_HOST')
    beanstalkd_port = env('BEANSTALKD_PORT')

    strava_client_id = env('STRAVA_CLIENT_ID')
    strava_client_secret = env('STRAVA_CLIENT_SECRET')
    strava_activity_cache_dir = env('STRAVA_ACTIVITY_CACHE_DIR')
    strava_activity_cache_dir = env('STRAVA_ACTIVITY_CACHE_DIR')

    wunderground_api_key = env('WUNDERGROUND_API_KEY')
    wunderground_cache_dir = env('WUNDERGROUND_CACHE_DIR')

    # This may not be correct/sufficient for newer instagram api anyway ...
    # instagram_client_id = env('INSTAGRAM_CLIENT_ID')
    # instagram_cache_dir = env('INSTAGRAM_CACHE_DIR')

    competition_teams = env('TEAMS')
    observer_teams = env('OBSERVER_TEAMS')

    start_date = env('START_DATE', postprocessor=lambda val: arrow.get(val).datetime)
    end_date = env('END_DATE', postprocessor=lambda val: arrow.get(val).datetime)

    upload_grace_period:timedelta = env('UPLOAD_GRACE_PERIOD_DAYS', postprocessor=lambda val: timedelta(days=val))

    exclude_keywords:List[str] = env('EXCLUDE_KEYWORDS')


config = Config()


def init_logging():
    logging.basicConfig(level=logging.DEBUG if config.debug else logging.INFO)


def init():
    init_logging()
    init_model(sqlalchemy_url=config.sqlalchemy_url)