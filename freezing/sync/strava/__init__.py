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
            athlete = meta.session_factory().query(Athlete).get(athlete)
        super(StravaClientForAthlete, self).__init__(access_token=athlete.access_token, rate_limit_requests=True)

