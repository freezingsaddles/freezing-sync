import logging
import re
from typing import List
from datetime import datetime

import arrow
from geoalchemy import WKTSpatialElement

from sqlalchemy import and_
from sqlalchemy.orm import joinedload

from freezing.sync.utils.cache import CachingActivityFetcher
from stravalib import unithelper

from stravalib import model as sm
from stravalib.exc import Fault
from stravalib.unithelper import timedelta_to_seconds

from freezing.model import meta
from freezing.model.orm import Athlete, Ride, RideEffort, RidePhoto, RideError, RideGeo, Team

from freezing.sync.config import config
from freezing.sync.exc import DataEntryError, CommandError, MultipleTeamsError, NoTeamsError

from . import StravaClientForAthlete, BaseSync


class AthleteSync(BaseSync):

    name = 'sync-athletes'
    description = 'Sync athletes.'

    def sync_athletes(self, max_records: int = None):

        with meta.transaction_context() as sess:

            # We iterate over all of our athletes that have access tokens.
            # (We can't fetch anything for those that don't.)

            q = sess.query(Athlete)
            q = q.filter(Athlete.access_token is not None)
            if max_records:
                self.logger.info("Limiting to {} records.".format(max_records))
                q = q.limit(max_records)

            for athlete in q.all():
                self.logger.info("Updating athlete: {0}".format(athlete))
                try:
                    client = StravaClientForAthlete(athlete)
                    strava_athlete = client.get_athlete()
                    self.register_athlete(strava_athlete, athlete.access_token)
                    self.register_athlete_team(strava_athlete, athlete)
                except:
                    self.logger.warning("Error registering athlete {0}".format(athlete), exc_info=True)

    def register_athlete(self,
                         strava_athlete: sm.Athlete,
                         access_token: str) -> Athlete:
        """
        Ensure specified athlete is added to database, returns athlete model.

        :return: The added athlete model object.
        :rtype: :class:`bafs.model.Athlete`
        """
        session = meta.scoped_session()
        athlete = session.query(Athlete).get(strava_athlete.id)

        if athlete is None:
            athlete = Athlete()

        athlete.id = strava_athlete.id
        athlete_name = \
            f'{strava_athlete.firstname} {strava_athlete.lastname}'
        athlete.name = athlete_name
        athlete.profile_photo = strava_athlete.profile
        athlete.access_token = access_token

        def already_exists(display_name) -> bool:
            return session.query(Athlete).filter(Athlete.id != athlete.id) \
                       .filter(Athlete.display_name == display_name) \
                       .count() > 0

        def unambiguous_display_name() -> str:
            display_name = athlete_name[:(2 + athlete_name.index(' '))]
            return display_name \
                if not already_exists(display_name) \
                else athlete_name

        # Only update the display name if it is either:
        # a new athlete, or the athlete name has changed
        try:
            if athlete is None or athlete_name != athlete.name:
                athlete.display_name = unambiguous_display_name()
        except:
            self.logger.exception(
                "Athlete name disambiguation error for {}".format(
                    strava_athlete.id),
                exc_info=True)
            athlete.display_name = athlete_name
        finally:
            session.add(athlete)
        return athlete


    def register_athlete_team(self, strava_athlete:sm.Athlete, athlete_model:Athlete) -> Team:
        """
        Updates db with configured team that matches the athlete's teams.

        Updates the passed-in Athlete model object with created/updated team.

        :param strava_athlete: The Strava model object for the athlete.
        :param athlete_model: The athlete model object.
        :return: The :class:`bafs.model.Team` object will be returned which matches
                 configured teams.
        :raise MultipleTeamsError: If this athlete is registered for multiple of
                                   the configured teams.  That won't work.
        :raise NoTeamsError: If no teams match.
        """

        all_teams = config.COMPETITION_TEAMS
        self.logger.info("Checking {0!r} against {1!r}".format(
            strava_athlete.clubs, all_teams))
        try:
            if strava_athlete.clubs is None:
                raise NoTeamsError(
                    "Athlete {0} ({1} {2}): No clubs returned- {3}. {4}.".format(
                        strava_athlete.id,
                        strava_athlete.firstname,
                        strava_athlete.lastname,
                        "Full Profile Access required",
                        "Please re-authorize"
                    )
                )
            matches = [c for c in strava_athlete.clubs if c.id in all_teams]
            self.logger.debug("Matched: {0!r}".format(matches))
            athlete_model.team = None
            if len(matches) > 1:
                # you can be on multiple teams
                # as long as only one is an official team
                matches = [c for c in matches
                           if c.id not in config.OBSERVER_TEAMS]
            if len(matches) > 1:
                self.logger.info("Multiple teams matched for {}: {}".format(
                    strava_athlete,
                    matches,
                    ))
                raise MultipleTeamsError(matches)
            if len(matches) == 0:
                # Fall back to main team if it is the only team they are in
                matches = [c for c in strava_athlete.clubs
                           if c.id == config.MAIN_TEAM]
            if len(matches) == 0:
                raise NoTeamsError(
                    "Athlete {0} ({1} {2}): {3} {4}".format(
                            strava_athlete.id,
                            strava_athlete.firstname,
                            strava_athlete.lastname,
                            "No teams matched ours. Teams defined:",
                            strava_athlete.clubs,
                            )
                )
            else:
                club = matches[0]
                # create the team row if it does not exist
                team = meta.scoped_session().query(Team).get(club.id)
                if team is None:
                    team = Team()
                team.id = club.id
                team.name = club.name
                team.leaderboard_exclude = club.id in config.OBSERVER_TEAMS
                athlete_model.team = team
                meta.scoped_session().add(team)
                return team
        finally:
            meta.scoped_session().commit()
