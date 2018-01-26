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
        if not isinstance(athlete, Athlete):
            athlete = meta.scoped_session().query(Athlete).get(athlete)
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
