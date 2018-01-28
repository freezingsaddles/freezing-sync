import os
import logging
from datetime import timedelta
from typing import List

from envparse import env

import arrow

from freezing.model import init_model

envfile = os.environ.get('APP_SETTINGS', os.path.join(os.getcwd(), '.env'))

if os.path.exists(envfile):
    env.read_envfile(envfile)


class Config:

    DEBUG = env('DEBUG')  # type: bool
    SQLALCHEMY_URL = env('SQLALCHEMY_URL')
    BEANSTALKD_HOST = env('BEANSTALKD_HOST', default='localhost')
    BEANSTALKD_PORT = env('BEANSTALKD_PORT', cast=int, default=11300)

    STRAVA_CLIENT_ID = env('STRAVA_CLIENT_ID')
    STRAVA_CLIENT_SECRET = env('STRAVA_CLIENT_SECRET')
    STRAVA_ACTIVITY_CACHE_DIR = env('STRAVA_ACTIVITY_CACHE_DIR', default='/data/cache/activities')

    WUNDERGROUND_API_KEY = env('WUNDERGROUND_API_KEY')
    WUNDERGROUND_CACHE_DIR = env('WUNDERGROUND_CACHE_DIR', default='/data/cache/weather')

    COMPETITION_TEAMS = env('TEAMS', cast=list, subcast=int, default=[])
    OBSERVER_TEAMS = env('OBSERVER_TEAMS', cast=list, subcast=int, default=[])

    START_DATE = env('START_DATE', postprocessor=lambda val: arrow.get(val).datetime)
    END_DATE = env('END_DATE', postprocessor=lambda val: arrow.get(val).datetime)

    UPLOAD_GRACE_PERIOD:timedelta = env('UPLOAD_GRACE_PERIOD_DAYS', cast=int, default=1, postprocessor=lambda val: timedelta(days=val))

    EXCLUDE_KEYWORDS:List[str] = env('EXCLUDE_KEYWORDS', cast=list, subcast=str, default=['#NoBAFS'])


config = Config()


def init_logging():
    logging.basicConfig(level=logging.DEBUG if config.DEBUG else logging.INFO)


def init():
    init_logging()
    init_model(sqlalchemy_url=config.SQLALCHEMY_URL)
