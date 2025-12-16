import abc
import logging
import time
from typing import Union

from freezing.model import meta
from freezing.model.orm import Athlete
from stravalib import Client

from freezing.sync.config import Config


class StravaClientForAthlete(Client):
    """
    Creates a StravaClient for the specified athlete.
    """

    def __init__(
        self,
        athlete: Union[int, Athlete],
        logger: logging.Logger = None,
    ):
        self.logger = logger or logging.getLogger(__name__)
        assert athlete, "No athlete ID or Athlete object provided."
        if athlete is None:
            raise ValueError("athlete may not be None")
        if not isinstance(athlete, Athlete):
            athlete_id = athlete
            athlete = meta.scoped_session().query(Athlete).get(athlete_id)
            if not athlete:
                raise ValueError(
                    "Athlete ID does not exist in database: {}".format(athlete_id)
                )
        super(StravaClientForAthlete, self).__init__(
            access_token=athlete.access_token, rate_limit_requests=True
        )
        self.refresh_access_token(athlete)

    def refresh_access_token(self, athlete: Athlete):
        assert athlete, "No athlete ID or Athlete object provided."
        if athlete.refresh_token is not None:
            an_hour_from_now = time.time() + 60 * 60
            if athlete.access_token is None or athlete.expires_at < an_hour_from_now:
                refresh_token = athlete.refresh_token
                self.logger.info(
                    "access token for athlete %s is stale, expires_at=%s",
                    athlete.id,
                    athlete.expires_at,
                )
            else:
                # Access token is still valid - no action needed
                refresh_token = None
                self.logger.info(
                    "access token for athlete %s is still valid ",
                    athlete.id,
                )
        elif athlete.access_token is not None:
            # Athlete has an access token but no refresh token yet.
            # Upgrade the forever token to the new tokens as described in:
            # https://developers.strava.com/docs/oauth-updates/#migration-instructions
            refresh_token = athlete.access_token
        else:
            raise ValueError(
                "athlete %s had no access or refresh token".format(athlete.id)
            )
        if refresh_token:
            self.logger.info("saving refresh token for athlete %s", athlete.id)
            token_dict = super().refresh_access_token(
                Config.STRAVA_CLIENT_ID,
                Config.STRAVA_CLIENT_SECRET,
                refresh_token,
            )
            self.access_token = token_dict["access_token"]
            athlete.access_token = token_dict["access_token"]
            athlete.refresh_token = token_dict["refresh_token"]
            athlete.expires_at = token_dict["expires_at"]
            meta.scoped_session().add(athlete)
            meta.scoped_session().commit()


class BaseSync(metaclass=abc.ABCMeta):
    @property
    @abc.abstractmethod
    def name(self):
        pass

    @property
    @abc.abstractmethod
    def description(self):
        pass

    def __init__(self, logger: logging.Logger = None):
        self.logger = logger or logging.getLogger(__name__)
