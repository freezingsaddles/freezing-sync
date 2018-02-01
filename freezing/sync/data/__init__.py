import abc
import logging
from typing import Union

from stravalib import Client

from freezing.model import meta
from freezing.model.orm import Athlete


class StravaClientForAthlete(Client):
    """
    Creates a StravaClient for the specified athlete.
    """

    def __init__(self, athlete: Union[int, Athlete]):
        assert athlete, "No athlete ID or Athlete object provided."
        if not isinstance(athlete, Athlete):
            athlete = meta.scoped_session().query(Athlete).get(athlete)
            if not athlete:
                raise ValueError("Athlete ID does not exist in database: {}".format(athlete_id))
        super(StravaClientForAthlete, self).__init__(access_token=athlete.access_token, rate_limit_requests=True)


class BaseSync(metaclass=abc.ABCMeta):

    @property
    @abc.abstractmethod
    def name(self):
        pass

    @property
    @abc.abstractmethod
    def description(self):
        pass

    def __init__(self, logger:logging.Logger = None):
        self.logger = logger or logging.getLogger(__name__)
