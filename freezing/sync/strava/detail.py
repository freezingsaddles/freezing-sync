import os
import json
import logging
import re
from typing import Dict, Any, List

from geoalchemy import WKTSpatialElement
from polyline.codec import PolylineCodec
from sqlalchemy import update, or_, and_
from sqlalchemy.orm import joinedload
from stravalib import unithelper

from stravalib.model import Activity, Stream, ActivityPhotoPrimary
from stravalib.unithelper import timedelta_to_seconds

from freezing.model import meta
from freezing.model.orm import Athlete, Ride, RideTrack, RideEffort, RidePhoto

from freezing.sync.config import config
from freezing.sync.exc import ConfigurationError, DataEntryError
from freezing.sync.utils import wktutils

from . import StravaClientForAthlete


class ActivityDetailsFetcher:

    name = 'sync-activity-detail'
    description = 'Sync activity details JSON.'

    def __init__(self, logger:logging.Logger = None):
        self.logger = logger or logging.getLogger(__name__)

    def cache_dir(self, athlete_id:int) -> str:
        """
        Gets the cache directory for specific athlete.
        :param athlete_id: The athlete ID.
        :return: The cache directory.
        """
        cache_basedir = config.strava_activity_cache_dir
        if not cache_basedir:
            raise ConfigurationError("STRAVA_ACTIVITY_CACHE_DIR not configured!")

        directory = os.path.join(cache_basedir, str(athlete_id))
        if not os.path.exists(directory):
            os.makedirs(directory)

        return directory

    def cache_activity(self, strava_activity: Activity, activity_json: Dict[str, Any]) -> str:
        """
        Writes activity to cache dir.

        :param strava_activity: The Strava activit
        :param activity_json: The raw JSON for the activity.
        :return: The path to the cached file.
        """
        directory = self.cache_dir(strava_activity.athlete.id)

        activity_fname = '{}.json'.format(strava_activity.id)
        cache_path = os.path.join(directory, activity_fname)

        with open(cache_path, 'w') as fp:
            fp.write(json.dumps(activity_json, indent=2))

        return cache_path

    def get_cached_activity_json(self, athlete_id: int, activity_id: Ride) -> Dict[str, Any]:
        """
        Retrieves raw activity from cached directory.

        :param ride: The Ride model object
        :return: A matched Strava Activity JSON object or None if there was no cache.
        """
        directory = self.cache_dir(athlete_id)

        activity_fname = '{}.json'.format(activity_id)

        cache_path = os.path.join(directory, activity_fname)

        activity_json = None
        if os.path.exists(cache_path):
            with open(cache_path, 'r') as fp:
                activity_json = json.load(fp)

        return activity_json

    def update_ride_from_activity(self, strava_activity:Activity, ride:Ride):
        """
        Refactoring to just set ride properties from the Strava Activity object.

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

        # We need to round so that "1.0" miles in strava is "1.0" miles when we convert back from meters.
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

        try:
            # Start by removing any existing segments for the ride.
            self.session.execute(RideEffort.__table__.delete().where(RideEffort.ride_id == strava_activity.id))

            # Then add them back in
            for se in strava_activity.segment_efforts:
                effort = RideEffort(id=se.id,
                                    ride_id=strava_activity.id,
                                    elapsed_time=timedelta_to_seconds(se.elapsed_time),
                                    segment_name=se.segment.name,
                                    segment_id=se.segment.id)

                self.logger.debug("Writing ride effort: {se_id}: {effort!r}".format(se_id=se.id,
                                                                            effort=effort.segment_name))

                self.session.add(effort)
                self.session.flush()

            ride.efforts_fetched = True

        except:
            self.logger.exception("Error adding effort for ride: {0}".format(ride))
            raise

    def _write_instagram_photo_primary(self, photo:ActivityPhotoPrimary, ride: Ride) -> RidePhoto:
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

        media = None

        # This doesn't work any more; Instagram changed their API to use OAuth.
        #
        # insta_client = insta.configured_instagram_client()
        # shortcode = re.search(r'/p/([^/]+)/', photo.urls['100']).group(1)
        # try:
        #     #self.logger.debug("Fetching Instagram media for shortcode: {}".format(shortcode))
        #     media = insta_client.media_shortcode(shortcode)
        # except (InstagramAPIError, InstagramClientError) as e:
        #     if e.status_code == 400:
        #         self.logger.warning("Instagram photo {} for ride {}; user is set to private".format(shortcode, ride))
        #     elif e.status_code == 404:
        #         self.logger.warning("Photo {} for ride {}; shortcode not found".format(shortcode, ride))
        #     else:
        #         self.logger.exception("Error fetching instagram photo {}".format(photo))

        p = RidePhoto()

        if media:
            p.id = media.id
            p.ref = media.link
            p.img_l = media.get_standard_resolution_url()
            p.img_t = media.get_thumbnail_url()
            if media.caption:
                p.caption = media.caption.text
        else:
            p.id = photo.id
            p.ref = re.match(r'(.+/)media\?size=.$', photo.urls['100']).group(1)
            p.img_l = photo.urls['600']
            p.img_t = photo.urls['100']

        p.ride_id = ride.id
        p.primary = True
        p.source = photo.source

        self.logger.debug("Writing (primary) Instagram ride photo: {!r}".format(p))

        self.session.add(p)
        self.session.flush()

        return p

    def _write_strava_photo_primary(self, photo, ride):
        """
        Writes a strava native (source=1) primary photo to db.

        :param photo: The primary photo from an activity.
        :type photo: stravalib.orm.ActivityPhotoPrimary
        :param ride: The db model object for ride.
        :type ride: bafs.orm.Ride
        :return: The newly added ride photo object.
        :rtype: bafs.orm.RidePhoto
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

        self.logger.debug("Writing (primary) Strava ride photo: {}".format(p))

        self.session.add(p)
        self.session.flush()
        return p
    
    def write_ride_photo_primary(self, strava_activity: Activity, ride: Ride):
        """
        Store primary photo for activity from the main detail-level activity.

        :param strava_activity: The Strava :class:`stravalib.orm.Activity` object.
        :type strava_activity: :class:`stravalib.orm.Activity`

        :param ride: The db model object for ride.
        :type ride: bafs.orm.Ride
        """
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
                self._write_strava_photo_primary(primary_photo, ride)
            else:
                self._write_instagram_photo_primary(primary_photo, ride)

    def execute(self, athlete_id: int = None, rewrite: bool = False, max_records: int = None,
                use_cache: bool = True, only_cache: bool = False):
        
        self.session = meta.session_factory()
        
        q = self.session.query(Ride)
        q = q.options(joinedload(Athlete))

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

                if use_cache:
                    activity_json = self.get_cached_activity_json(athlete_id=ride.athlete_id, activity_id=ride.id)
                else:
                    activity_json = None

                if activity_json is None:
                    if only_cache:
                        self.logger.info("[CACHE-MISS] Skipping ride {} since there is no cached version.")
                        continue

                    self.logger.info("[CACHE-MISS] Fetching activity detail for {!r}".format(ride))
                    # We do this manually, so that we can cache the JSON for later use.
                    activity_json = client.protocol.get('/activities/{id}', id=ride.id, include_all_efforts=True)
                    strava_activity = Activity.deserialize(activity_json, bind_client=client)

                    try:
                        self.logger.info("Caching activity {!r}".format(ride))
                        self.cache_activity(strava_activity, activity_json)
                    except:
                        self.logger.error("Error caching activity {} (ignoring)".format(strava_activity),
                                  exc_info=self.logger.isEnabledFor(logging.DEBUG))

                else:
                    strava_activity = Activity.deserialize(activity_json, bind_client=client)
                    self.logger.info("[CACHE-HIT] Using cached activity detail for {!r}".format(ride))

                # try:
                #     self.logger.info("Writing out GPS track for {!r}".format(ride))
                #     data.write_ride_track(strava_activity, ride)
                # except:
                #     self.logger.error("Error writing track for activity {0}, athlete {1}".format(ride.id, ride.athlete),
                #                       exc_info=self.logger.isEnabledFor(logging.DEBUG))
                #     raise

                # We do this just to take advantage of the use-cache/only-cache feature for reprocessing activities.
                self.update_ride_from_activity(strava_activity=strava_activity, ride=ride)
                self.session.flush()

                try:
                    self.logger.info("Writing out efforts for {!r}".format(ride))
                    self.write_ride_efforts(strava_activity, ride)
                    self.session.flush()
                except:
                    self.logger.error("Error writing efforts for activity {0}, athlete {1}".format(ride.id, ride.athlete),
                                      exc_info=self.logger.isEnabledFor(logging.DEBUG))
                    raise

                try:
                    self.logger.info("Writing out primary photo for {!r}".format(ride))
                    if strava_activity.total_photo_count > 0:
                        self.write_ride_photo_primary(strava_activity, ride)
                    else:
                        self.logger.debug ("No photos for {!r}".format(ride))
                except:
                    self.logger.error("Error writing primary photo for activity {}, athlete {}".format(ride.id, ride.athlete),
                                      exc_info=self.logger.isEnabledFor(logging.DEBUG))
                    raise

                ride.detail_fetched = True
                self.session.commit()

            except:
                self.logger.exception("Error fetching/writing activity detail {}, athlete {}".format(ride.id, ride.athlete))
                self.session.rollback()
