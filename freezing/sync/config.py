import os
import logging
from datetime import timedelta, tzinfo
import pytz
from typing import List
from datadog import initialize, DogStatsd

from colorlog import ColoredFormatter
from envparse import env

import arrow

from freezing.model import init_model

envfile = os.environ.get("APP_SETTINGS", os.path.join(os.getcwd(), ".env"))

if os.path.exists(envfile):
    env.read_envfile(envfile)


class Config:

    DEBUG = env("DEBUG")  # type: bool
    SQLALCHEMY_URL = env("SQLALCHEMY_URL")
    BEANSTALKD_HOST = env("BEANSTALKD_HOST", default="localhost")
    BEANSTALKD_PORT = env("BEANSTALKD_PORT", cast=int, default=11300)

    STRAVA_CLIENT_ID = env("STRAVA_CLIENT_ID")
    STRAVA_CLIENT_SECRET = env("STRAVA_CLIENT_SECRET")
    STRAVA_ACTIVITY_CACHE_DIR = env(
        "STRAVA_ACTIVITY_CACHE_DIR", default="/data/cache/activities"
    )

    DARK_SKY_API_KEY = env("DARK_SKY_API_KEY")
    DARK_SKY_CACHE_DIR = env("DARK_SKY_CACHE_DIR", default="/data/cache/weather")

    COMPETITION_TEAMS = env("TEAMS", cast=list, subcast=int, default=[])
    OBSERVER_TEAMS = env("OBSERVER_TEAMS", cast=list, subcast=int, default=[])
    MAIN_TEAM = env("MAIN_TEAM", cast=int, default=0)

    START_DATE = env("START_DATE", postprocessor=lambda val: arrow.get(val).datetime)
    END_DATE = env("END_DATE", postprocessor=lambda val: arrow.get(val).datetime)

    TIMEZONE: tzinfo = env(
        "TIMEZONE",
        default="America/New_York",
        postprocessor=lambda val: pytz.timezone(val),
    )

    UPLOAD_GRACE_PERIOD: timedelta = env(
        "UPLOAD_GRACE_PERIOD_DAYS",
        cast=int,
        default=1,
        postprocessor=lambda val: timedelta(days=val),
    )

    EXCLUDE_KEYWORDS: List[str] = env(
        "EXCLUDE_KEYWORDS", cast=list, subcast=str, default=["#NoBAFS"]
    )

    DATADOG_API_KEY = env("DATADOG_API_KEY", default=None)
    DATADOG_APP_KEY = env("DATADOG_APP_KEY", default=None)
    DATADOG_HOST = env("DATADOG_HOST", default="datadog.container")
    DATADOG_PORT = env("DATADOG_PORT", cast=int, default=8125)


config = Config()


def init_logging(loglevel: int = logging.INFO, color: bool = False):
    """
    Initialize the logging subsystem and create a logger for this class, using passed in optparse options.

    :param level: The log level (e.g. logging.DEBUG)
    :return:
    """
    ch = logging.StreamHandler()
    ch.setLevel(loglevel)

    if color:
        formatter = ColoredFormatter(
            "%(log_color)s%(levelname)-8s%(reset)s [%(name)s] %(message)s",
            datefmt=None,
            reset=True,
            log_colors={
                "DEBUG": "cyan",
                "INFO": "green",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "red",
            },
        )
    else:
        formatter = logging.Formatter("%(levelname)-8s [%(name)s] %(message)s")

    ch.setFormatter(formatter)

    loggers = [
        logging.getLogger("freezing"),
        logging.getLogger("stravalib"),
        logging.getLogger("requests"),
        logging.root,
    ]

    logging.root.addHandler(ch)

    for l in loggers:
        if l is logging.root:
            l.setLevel(logging.DEBUG)
        else:
            l.setLevel(logging.INFO)


statsd = DogStatsd(host=config.DATADOG_HOST, port=config.DATADOG_PORT)
