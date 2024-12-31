import logging
import os
from datetime import timedelta, tzinfo
from typing import List

import arrow
import pytz
from colorlog import ColoredFormatter
from datadog import DogStatsd
from envparse import env

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

    VISUAL_CROSSING_API_KEY = env("VISUAL_CROSSING_API_KEY")
    VISUAL_CROSSING_CACHE_DIR = env(
        "VISUAL_CROSSING_CACHE_DIR", default="/data/cache/weather"
    )

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
    DATADOG_HOST = env("DATADOG_HOST", default="localhost")
    DATADOG_PORT = env("DATADOG_PORT", cast=int, default=8125)

    REQUEUE_DELAY = env("REQUEUE_DELAY", cast=int, default=300)


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

    # This logger is very noisy and spits out WARNING level
    # messages that are not very useful, such as:
    # "WARNING  [stravalib.attributes.EntityAttribute] Unable to set attribute visibility on entity <Activity id=13209828474 name=None>"
    # Silence it except for CRITICAL messages.

    logging.getLogger("stravalib.attributes").setLevel(logging.CRITICAL)


statsd = DogStatsd(host=config.DATADOG_HOST, port=config.DATADOG_PORT)
