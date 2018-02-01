import logging
import re
from typing import List, Optional
from datetime import datetime

import arrow
from geoalchemy import WKTSpatialElement

from sqlalchemy import and_, func
from sqlalchemy.orm import joinedload

from freezing.sync.utils.cache import CachingActivityFetcher
from stravalib import unithelper

from stravalib.model import Activity, ActivityPhotoPrimary
from stravalib.unithelper import timedelta_to_seconds

from freezing.model import meta
from freezing.model.orm import Athlete, Ride, RideEffort, RidePhoto, RideError, RideGeo

from freezing.sync.config import config
from freezing.sync.exc import DataEntryError, CommandError, InvalidAuthorizationToken

from . import StravaClientForAthlete, BaseSync


class ActivitySync(BaseSync):

    name = 'sync-activity'
    description = 'Sync activities.'

    def update_ride_basic(self, strava_activity:Activity, ride:Ride):
        """
        Set basic ride properties from the Strava Activity object.

        :param strava_activity: The Strava Activity
        :param ride: The ride model object.
        """
        # Should apply to both new and preexisting rides ...
        # If there are multiple instagram photos, then request syncing of non-primary photos too.

        if strava_activity.photo_count > 1 and ride.photos_fetched is None:
            self.logger.debug("Scheduling non-primary photos sync for {!r}".format(ride))
            ride.photos_fetched = False

        ride.private = bool(strava_activity.private)
        ride.name = strava_activity.name
        ride.start_date = strava_activity.start_date_local

        # We need to round so that "1.0" miles in data is "1.0" miles when we convert back from meters.
        ride.distance = round(float(unithelper.miles(strava_activity.distance)), 3)

        ride.average_speed = float(unithelper.mph(strava_activity.average_speed))
        ride.maximum_speed = float(unithelper.mph(strava_activity.max_speed))
        ride.elapsed_time = timedelta_to_seconds(strava_activity.elapsed_time)
        ride.moving_time = timedelta_to_seconds(strava_activity.moving_time)

        location_parts = []
        if strava_activity.location_city:
            location_parts.append(strava_activity.location_city)
        if strava_activity.location_state:
            location_parts.append(strava_activity.location_state)
        location_str = ', '.join(location_parts)

        ride.location = location_str

        ride.commute = strava_activity.commute
        ride.trainer = strava_activity.trainer
        ride.manual = strava_activity.manual
        ride.elevation_gain = float(unithelper.feet(strava_activity.total_elevation_gain))
        ride.timezone = str(strava_activity.timezone)

        # # Short-circuit things that might result in more obscure db errors later.
        if ride.elapsed_time is None:
            raise DataEntryError("Activities cannot have null elapsed time.")

        if ride.moving_time is None:
            raise DataEntryError("Activities cannot have null moving time.")

        if ride.distance is None:
            raise DataEntryError("Activities cannot have null distance.")

        self.logger.debug("Writing ride for {athlete!r}: \"{ride!r}\" on {date}".format(athlete=ride.athlete.name,
                                                                                ride=ride.name,
                                                                                date=ride.start_date.strftime(
                                                                                    '%m/%d/%y')))

    def write_ride_efforts(self, strava_activity: Activity, ride: Ride):
        """
        Writes out all effort associated with a ride to the database.

        :param strava_activity: The :class:`stravalib.orm.Activity` that is associated with this effort.
        :param ride: The db model object for ride.
        """
        session = meta.scoped_session()

        try:
            # Start by removing any existing segments for the ride.
            session.execute(RideEffort.__table__.delete().where(RideEffort.ride_id == strava_activity.id))

            # Then add them back in
            for se in strava_activity.segment_efforts:
                effort = RideEffort(id=se.id,
                                    ride_id=strava_activity.id,
                                    elapsed_time=timedelta_to_seconds(se.elapsed_time),
                                    segment_name=se.segment.name,
                                    segment_id=se.segment.id)

                self.logger.debug("Writing ride effort: {se_id}: {effort!r}".format(se_id=se.id,
                                                                            effort=effort.segment_name))

                session.add(effort)
                session.flush()

            ride.efforts_fetched = True

        except:
            self.logger.exception("Error adding effort for ride: {0}".format(ride))
            raise

    def _make_photo_from_instagram(self, photo:ActivityPhotoPrimary, ride: Ride) -> Optional[RidePhoto]:
        """
        Writes an instagram primary photo to db.

        :param photo: The primary photo from an activity.
        :param ride: The db model object for ride.
        :return: The newly added ride photo object.
        """

        # Here is when we have an Instagram photo as primary:
        #  u'photos': {u'count': 1,
        #   u'primary': {u'id': 106409096,
        #    u'source': 2,
        #    u'unique_id': None,
        #    u'urls': {u'100': u'https://instagram.com/p/88qaqZvrBI/media?size=t',
        #     u'600': u'https://instagram.com/p/88qaqZvrBI/media?size=l'}},
        #   u'use_prima ry_photo': False},

        p = RidePhoto()
        p.id = photo.id
        p.ref = re.match(r'(.+/)media\?size=.$', photo.urls['100']).group(1)
        p.img_l = photo.urls['600']
        p.img_t = photo.urls['100']

        p.ride_id = ride.id
        p.primary = True
        p.source = photo.source

        self.logger.debug("Writing (primary) Instagram ride photo: {!r}".format(p))

        return p

    def _make_photo_from_native(self, photo: ActivityPhotoPrimary, ride: Ride) -> Optional[RidePhoto]:
        """
        Writes a data native (source=1) primary photo to db.

        :param photo: The primary photo from an activity.
        :param ride: The db model object for ride.
        :return: The newly added ride photo object.
        """
        # 'photos': {u'count': 1,
        #   u'primary': {u'id': None,
        #    u'source': 1,
        #    u'unique_id': u'35453b4b-0fc1-46fd-a824-a4548426b57d',
        #    u'urls': {u'100': u'https://dgtzuqphqg23d.cloudfront.net/Vvm_Mcfk1SP-VWdglQJImBvKzGKRJrHlNN4BqAqD1po-128x96.jpg',
        #     u'600': u'https://dgtzuqphqg23d.cloudfront.net/Vvm_Mcfk1SP-VWdglQJImBvKzGKRJrHlNN4BqAqD1po-768x576.jpg'}},
        #   u'use_primary_photo': False},

        if not photo.urls:
            self.logger.warning("Photo {} present, but has no URLs (skipping)".format(photo))
            return None

        p = RidePhoto()
        p.id = photo.unique_id
        p.primary = True
        p.source = photo.source
        p.ref = None
        p.img_l = photo.urls['600']
        p.img_t = photo.urls['100']
        p.ride_id = ride.id

        self.logger.debug("Creating (primary) native ride photo: {}".format(p))

        return p

    def write_ride_photo_primary(self, strava_activity: Activity, ride: Ride):
        """
        Store primary photo for activity from the main detail-level activity.

        :param strava_activity: The Strava :class:`stravalib.orm.Activity` object.
        :type strava_activity: :class:`stravalib.orm.Activity`

        :param ride: The db model object for ride.
        :type ride: bafs.orm.Ride
        """
        session = meta.scoped_session()

        # If we have > 1 instagram photo, then we don't do anything.
        if strava_activity.photo_count > 1:
            self.logger.debug("Ignoring basic sync for {} since there are > 1 instagram photos.")
            return

        # Start by removing any priamry photos for this ride.
        meta.engine.execute(RidePhoto.__table__.delete().where(and_(RidePhoto.ride_id == strava_activity.id,
                                                                    RidePhoto.primary == True)))

        primary_photo = strava_activity.photos.primary

        if primary_photo:
            if primary_photo.source == 1:
                p = self._make_photo_from_native(primary_photo, ride)
            else:
                p = self._make_photo_from_instagram(primary_photo, ride)
            session.add(p)
            session.flush()

    def sync_rides_detail(self, athlete_id: int = None, rewrite: bool = False, max_records: int = None,
                          use_cache: bool = True, only_cache: bool = False):

        session = meta.scoped_session()

        q = session.query(Ride)
        q = q.options(joinedload(Ride.athlete))

        # TODO: Construct a more complex query to catch photos_fetched=False, track_fetched=False, etc.
        q = q.filter(Ride.private==False)

        if not rewrite:
            q = q.filter(Ride.detail_fetched==False)

        if athlete_id:
            self.logger.info("Filtering activity details for {}".format(athlete_id))
            q = q.filter(Ride.athlete_id == athlete_id)

        if max_records:
            self.logger.info("Limiting to {} records".format(max_records))
            q = q.limit(max_records)

        use_cache = use_cache or only_cache

        self.logger.info("Fetching details for {} activities".format(q.count()))

        for ride in q:
            try:
                client = StravaClientForAthlete(ride.athlete)

                af = CachingActivityFetcher(cache_basedir=config.STRAVA_ACTIVITY_CACHE_DIR, client=client)

                strava_activity = af.fetch(athlete_id=ride.athlete_id, object_id=ride.id,
                                           use_cache=use_cache, only_cache=only_cache)

                self.update_ride_complete(strava_activity=strava_activity, ride=ride)

                session.commit()

            except:
                self.logger.exception("Error fetching/writing activity detail {}, athlete {}".format(ride.id, ride.athlete))
                session.rollback()

    def delete_activity(self, *, athlete_id: int, activity_id: int):
        session = meta.scoped_session()
        ride = session.query(Ride).filter(Ride.id == activity_id).filter(Ride.athlete_id == athlete_id).one_or_none()
        if ride:
            session.delete(ride)
            session.commit()
        else:
            self.logger.warning("Unable to find ride {} for athlete {} to remove.".format(activity_id, athlete_id))

    def fetch_and_store_actvitiy_detail(self, *, athlete_id: int, activity_id:int, use_cache: bool = False):

        session = meta.scoped_session()

        self.logger.info("Fetching detailed activity athlete_id={}, activity_id={}".format(athlete_id, activity_id))

        athlete = session.query(Athlete).get(athlete_id)

        try:
            client = StravaClientForAthlete(athlete)

            af = CachingActivityFetcher(cache_basedir=config.STRAVA_ACTIVITY_CACHE_DIR, client=client)

            strava_activity = af.fetch(athlete_id=athlete_id, object_id=activity_id,
                                       use_cache=use_cache)

            ride = self.write_ride(strava_activity)
            self.update_ride_complete(strava_activity=strava_activity, ride=ride)

            session.commit()

        except:
            self.logger.exception(
                "Error fetching/writing activity detail {}, athlete {}".format(activity_id, athlete_id))
            session.rollback()
            raise

    def update_ride_complete(self, strava_activity: Activity, ride: Ride):
        """
        Updates all ride data from a fully-populated Strava `Activity`.

        :param strava_activity: The Activity that has been populated from detailed fetch.
        :param ride: The database ride object to update.
        """
        session = meta.scoped_session()

        # We do this just to take advantage of the use-cache/only-cache feature for reprocessing activities.
        self.update_ride_basic(strava_activity=strava_activity, ride=ride)
        session.flush()
        try:
            self.logger.info("Writing out efforts for {!r}".format(ride))
            self.write_ride_efforts(strava_activity, ride)
            session.flush()
        except:
            self.logger.error("Error writing efforts for activity {0}, athlete {1}".format(ride.id, ride.athlete),
                              exc_info=self.logger.isEnabledFor(logging.DEBUG))
            raise
        try:
            self.logger.info("Writing out primary photo for {!r}".format(ride))
            if strava_activity.total_photo_count > 0:
                self.write_ride_photo_primary(strava_activity, ride)
            else:
                self.logger.debug("No photos for {!r}".format(ride))
        except:
            self.logger.error("Error writing primary photo for activity {}, athlete {}".format(ride.id, ride.athlete),
                              exc_info=self.logger.isEnabledFor(logging.DEBUG))
            raise
        ride.detail_fetched = True

    def list_rides(self, athlete:Athlete, start_date:datetime, end_date:datetime,
                   exclude_keywords:List[str] = None) -> List[Activity]:
        """
        List all of the rides for individual athlete.

        :param athlete: The Athlete model object.
        :param start_date: The date to start listing rides.

        :param exclude_keywords: A list of keywords to use for excluding rides from the results (e.g. "#NoBAFS")

        :return: list of activity objects for rides in reverse chronological order.
        """
        client = StravaClientForAthlete(athlete)

        if exclude_keywords is None:
            exclude_keywords = []

        # Remove tz, since we are dealing with local times for activities
        end_date = end_date.replace(tzinfo=None)

        def is_excluded(activity):
            activity_end_date = (activity.start_date_local + activity.elapsed_time)
            if end_date and activity_end_date > end_date:
                self.logger.info(
                    "Skipping ride {0} ({1!r}) because date ({2}) is after competition end date ({3})".format(
                        activity.id,
                        activity.name,
                        activity_end_date,
                        end_date))
                return True

            for keyword in exclude_keywords:
                if keyword.lower() in activity.name.lower():
                    self.logger.info("Skipping ride {0} ({1!r}) due to presence of exclusion keyword: {2!r}".format(activity.id,
                                                                                                           activity.name,
                                                                                                           keyword))
                    return True
            else:
                return False

        activities = client.get_activities(after=start_date, limit=None)  # type: List[Activity]
        filtered_rides = [a for a in activities if
                          ((a.type == Activity.RIDE or a.type == Activity.EBIKERIDE)
                           and not a.manual and not a.trainer and not is_excluded(a))]

        return filtered_rides

    def write_ride(self, activity: Activity) -> Ride:
        """
        Takes the specified activity and writes it to the database.

        :param activity: The Strava :class:`stravalib.orm.Activity` object.

        :return: A tuple including the written Ride model object, whether to resync segment efforts, and whether to resync photos.
        :rtype: bafs.orm.Ride
        """
        session = meta.scoped_session()
        if activity.start_latlng:
            start_geo = WKTSpatialElement('POINT({lon} {lat})'.format(lat=activity.start_latlng.lat,
                                                                      lon=activity.start_latlng.lon))
        else:
            start_geo = None

        if activity.end_latlng:
            end_geo = WKTSpatialElement('POINT({lon} {lat})'.format(lat=activity.end_latlng.lat,
                                                                    lon=activity.end_latlng.lon))
        else:
            end_geo = None

        athlete_id = activity.athlete.id

        # Fail fast for invalid data (this can happen with manual-entry rides)
        assert activity.elapsed_time is not None
        assert activity.moving_time is not None
        assert activity.distance is not None

        # Find the model object for that athlete (or create if doesn't exist)
        athlete = session.query(Athlete).get(athlete_id)
        if not athlete:
            # The athlete has to exist since otherwise we wouldn't be able to query their rides
            raise ValueError("Somehow you are attempting to write rides for an athlete not found in the database.")

        if start_geo is not None or end_geo is not None:
            ride_geo = RideGeo()
            ride_geo.start_geo = start_geo
            ride_geo.end_geo = end_geo
            ride_geo.ride_id = activity.id
            session.merge(ride_geo)

        ride = session.query(Ride).get(activity.id)
        new_ride = (ride is None)
        if ride is None:
            ride = Ride(activity.id)

        if new_ride:

            # Set the "workflow flags".  These all default to False in the database.  The value of NULL means
            # that the workflow flag does not apply (e.g. do not bother fetching this)

            ride.detail_fetched = False  # Just to be explicit

            if not activity.manual:
                ride.track_fetched = False

            # photo_count refers to instagram photos
            if activity.photo_count > 1:
                ride.photos_fetched = False
            else:
                ride.photos_fetched = None

        else:
            # If ride has been cropped, we re-fetch it.
            if round(ride.distance, 2) != round(float(unithelper.miles(activity.distance)), 2):
                self.logger.info("Queing resync of details for activity {0!r}: "
                                 "distance mismatch ({1} != {2})".format(activity,
                                                                         ride.distance,
                                                                         unithelper.miles(activity.distance)))
                ride.detail_fetched = False
                ride.track_fetched = False

        ride.athlete = athlete

        self.update_ride_basic(strava_activity=activity, ride=ride)

        session.add(ride)

        return ride

    def _sync_rides(self, start_date:datetime, end_date:datetime, athlete, rewrite:bool = False):

        sess = meta.scoped_session()

        api_ride_entries = self.list_rides(athlete=athlete, start_date=start_date, end_date=end_date,
                                           exclude_keywords=config.EXCLUDE_KEYWORDS)

        # Because MySQL doesn't like it and we are not storing tz info in the db.
        start_notz = start_date.replace(tzinfo=None)

        q = sess.query(Ride)
        q = q.filter(and_(Ride.athlete_id == athlete.id,
                          Ride.start_date >= start_notz))
        db_rides = q.all()

        # Quickly filter out only the rides that are not in the database.
        returned_ride_ids = set([r.id for r in api_ride_entries])
        stored_ride_ids = set([r.id for r in db_rides])
        new_ride_ids = list(returned_ride_ids - stored_ride_ids)
        removed_ride_ids = list(stored_ride_ids - returned_ride_ids)

        num_rides = len(api_ride_entries)

        ride_ids_needing_detail = []
        ride_ids_needing_streams = []

        for (i, strava_activity) in enumerate(api_ride_entries):
            self.logger.debug("Processing ride: {0} ({1}/{2})".format(strava_activity.id, i + 1, num_rides))

            if rewrite or not strava_activity.id in stored_ride_ids:
                try:
                    ride = self.write_ride(strava_activity)
                    self.logger.info("[NEW RIDE]: {id} {name!r} ({i}/{num}) ".format(id=strava_activity.id,
                                                                                     name=strava_activity.name,
                                                                                     i=i + 1,
                                                                                     num=num_rides))
                    sess.commit()
                except Exception as x:
                    self.logger.debug(
                        "Error writing out ride, will attempt to add/update RideError: {0}".format(strava_activity.id))
                    sess.rollback()
                    try:
                        ride_error = sess.query(RideError).get(strava_activity.id)
                        if ride_error is None:
                            self.logger.exception(
                                "[ERROR] Unable to write ride (skipping): {0}".format(strava_activity.id))
                            ride_error = RideError()
                        else:
                            # We already have a record of the error, so log that message with less verbosity.
                            self.logger.warning(
                                "[ERROR] Unable to write ride (skipping): {0}".format(strava_activity.id))

                        ride_error.athlete_id = athlete.id
                        ride_error.id = strava_activity.id
                        ride_error.name = strava_activity.name
                        ride_error.start_date = strava_activity.start_date_local
                        ride_error.reason = str(x)
                        ride_error.last_seen = datetime.now()  # FIXME: TZ?
                        sess.add(ride_error)

                        sess.commit()
                    except:
                        self.logger.exception("Error adding ride-error entry.")
                else:
                    try:
                        # If there is an error entry, then we should remove it.
                        q = sess.query(RideError)
                        q = q.filter(RideError.id == ride.id)
                        deleted = q.delete(synchronize_session=False)
                        if deleted:
                            self.logger.info("Removed matching error-ride entry for {0}".format(strava_activity.id))
                        sess.commit()
                    except:
                        self.logger.exception("Error maybe-clearing ride-error entry.")

                    if ride.detail_fetched is False:
                        ride_ids_needing_detail.append(ride.id)

                    if ride.track_fetched is False:
                        ride_ids_needing_streams.append(ride.id)

            else:
                self.logger.debug("[SKIPPED EXISTING]: {id} {name!r} ({i}/{num}) ".format(id=strava_activity.id,
                                                                                          name=strava_activity.name,
                                                                                          i=i + 1,
                                                                                          num=num_rides))

        # Remove any rides that are in the database for this athlete that were not in the returned list.
        if removed_ride_ids:
            q = sess.query(Ride)
            q = q.filter(Ride.id.in_(removed_ride_ids))
            deleted = q.delete(synchronize_session=False)
            self.logger.info("Removed {0} no longer present rides for athlete {1}.".format(deleted, athlete))
        else:
            self.logger.debug("(No removed rides for athlete {0}.)".format(athlete))

        sess.commit()

    def sync_rides_distributed(self, total_segments: int, segment: int, start_date: datetime = None,
                               end_date:datetime = None):
        """

        :param total_segments: The number of segments to divide athletes into (e.g. 24 if this is being run hourly)
        :param segment: Which segment (0-based) to select.
        :param start_date: Will default to competition start.
        :param end_date: Will default to competition end.
        """

        sess = meta.scoped_session()

        q = sess.query(Athlete)
        q = q.filter(Athlete.access_token != None)
        q = q.filter(func.mod(Athlete.id, total_segments) == segment)
        athletes: List[Athlete] = q.all()
        self.logger.info("Selecting segment {} / {}, found {} athletes".format(segment, total_segments, len(athletes)))
        athlete_ids = [a.id for a in athletes]
        if athlete_ids:
            return self.sync_rides(start_date=start_date, end_date=end_date, athlete_ids=athlete_ids)

    def sync_rides(self, start_date: datetime = None, end_date:datetime = None, rewrite:bool = False,
                   force: bool = False, athlete_ids: List[int] = None):

        sess = meta.scoped_session()

        if start_date is None:
            start_date = config.START_DATE

        if end_date is None:
            end_date = config.END_DATE

        self.logger.debug("Fetching rides newer than {} and older than {}".format(start_date, end_date))

        if (arrow.now() > (end_date + config.UPLOAD_GRACE_PERIOD)) and not force:
            raise CommandError("Current time is after competition end date + grace "
                               "period, not syncing rides. (Use `force` to override.)")

        if rewrite:
            self.logger.info("Rewriting existing ride data.")

        # We iterate over all of our athletes that have access tokens.  (We can't fetch anything
        # for those that don't.)
        q = sess.query(Athlete)
        q = q.filter(Athlete.access_token != None)

        if athlete_ids is not None:
            q = q.filter(Athlete.id.in_(athlete_ids))

        # Also only fetch athletes that have teams configured.  This may not be strictly necessary
        # but this is a team competition, so not a lot of value in pulling in data for those
        # without teams.
        # (The way the athlete sync works, athletes will only be configured for a single team
        # that is one of the configured competition teams.)
        q = q.filter(Athlete.team_id != None)

        for athlete in q.all():
            assert isinstance(athlete, Athlete)
            self.logger.info("Fetching rides for athlete: {0}".format(athlete))
            try:
                self._sync_rides(start_date=start_date, end_date=end_date, athlete=athlete, rewrite=rewrite)
            except InvalidAuthorizationToken:
                self.logger.error("Invalid authorization token for {} (removing)".format(athlete))
                athlete.access_token = None
                sess.add(athlete)
                sess.commit()
