import logging
from typing import Dict

from freezing.model import meta
from freezing.model.orm import Athlete, Ride, RideGeo, RideTrack
from geoalchemy2.elements import WKTElement
from sqlalchemy import and_
from sqlalchemy.orm import joinedload
from stravalib.exc import ObjectNotFound
from stravalib.model import StreamSet

from freezing.sync.config import config
from freezing.sync.exc import ActivityNotFound
from freezing.sync.utils import wktutils
from freezing.sync.utils.cache import CachingStreamFetcher

from . import BaseSync, StravaClientForAthlete


class StreamSync(BaseSync):
    name = "sync-activity-streams"
    description = "Sync activity streams (GPS, etc.) JSON."

    def sync_streams(
        self,
        athlete_id: int = None,
        rewrite: bool = False,
        max_records: int = None,
        use_cache: bool = True,
        only_cache: bool = False,
    ):
        session = meta.scoped_session()

        q = session.query(Ride).options(joinedload(Ride.athlete))

        # We do not fetch streams for private rides.  Or manual rides (since there would be none).
        q = q.filter(and_(Ride.private is False, Ride.manual is False))

        if not rewrite:
            q = q.filter(
                Ride.track_fetched is False,
            )

        if athlete_id:
            self.logger.info("Filtering activity details for {}".format(athlete_id))
            q = q.filter(Ride.athlete_id == athlete_id)

        if max_records:
            self.logger.info("Limiting to {} records".format(max_records))
            q = q.limit(max_records)

        use_cache = use_cache or only_cache

        self.logger.info("Fetching gps tracks for {} activities".format(q.count()))

        for ride in q:
            try:
                client = StravaClientForAthlete(ride.athlete)
                sf = CachingStreamFetcher(
                    cache_basedir=config.STRAVA_ACTIVITY_CACHE_DIR, client=client
                )

                # Bypass the cache if we appear to be trying to refetch the ride because of change.
                # This is a different bypass cache behaviour to efforts, but the code is opaque and
                # effects uncertain. This field is set to false when a ride is resynced because its
                # distance has changed. So good to avoid cache in that case. However it's also set
                # to false in other cases maybe probably.
                bypass_cache = not ride.track_fetched

                streams = sf.fetch(
                    athlete_id=ride.athlete_id,
                    object_id=ride.id,
                    use_cache=use_cache and not bypass_cache,
                    only_cache=only_cache,
                )
                if streams:
                    self.write_ride_streams(streams, ride)
                    session.commit()
                else:
                    self.logger.debug("No streams for {!r} (skipping)".format(ride))
            except Exception:
                self.logger.exception(
                    "Error fetching/writing activity streams for "
                    "{}, athlete {}".format(ride, ride.athlete),
                    exc_info=True,
                )
                session.rollback()

    def fetch_and_store_activity_streams(
        self, *, athlete_id: int, activity_id: int, use_cache: bool = False
    ):
        with meta.transaction_context() as session:
            self.logger.info(
                "Fetching activity streams for athlete_id={}, activity_id={}".format(
                    athlete_id, activity_id
                )
            )

            ride = session.get(Ride, activity_id, options=[joinedload(Ride.athlete)])
            if not ride:
                raise RuntimeError("Cannot load streams before fetching activity.")

            try:
                client = StravaClientForAthlete(ride.athlete)
                sf = CachingStreamFetcher(
                    cache_basedir=config.STRAVA_ACTIVITY_CACHE_DIR, client=client
                )
                streams = sf.fetch(
                    athlete_id=athlete_id,
                    object_id=activity_id,
                    use_cache=use_cache,
                    only_cache=False,
                )
                if streams:
                    self.write_ride_streams(streams, ride)
                    session.commit()
                else:
                    self.logger.debug("No streams for {!r} (skipping)".format(ride))
            except ObjectNotFound:
                raise ActivityNotFound(
                    "Streams not found for {}, athlete {}".format(ride, ride.athlete)
                )
            except Exception:
                self.logger.exception(
                    "Error fetching/writing activity streams for "
                    "{}, athlete {}".format(ride, ride.athlete),
                    exc_info=True,
                )
                raise

    def write_ride_streams(self, streams: StreamSet, ride: Ride):
        """
        Store GPS track for activity as geometry (linestring) and json types in db.

        :param streams: The Strava streams.
        :param ride: The db model object for ride.
        """
        session = meta.scoped_session()
        try:
            streams_dict: Dict[str, StreamSet] = {s.type: s for s in streams}

            lonlat_points = [(lon, lat) for (lat, lon) in streams_dict["latlng"].data]

            # mysql does not admit the possibility of one point in a line
            if len(lonlat_points) < 2:
                raise ValueError("Insufficient data points in latlng streams.")

        except (KeyError, ValueError) as x:
            self.logger.info(
                "No GPS track for activity {} (skipping): {}".format(ride, x),
                exc_info=self.logger.isEnabledFor(logging.DEBUG),
            )
            ride.track_fetched = None
        else:
            # Start by removing any existing segments for the ride.
            session.execute(
                RideTrack.__table__.delete().where(RideTrack.ride_id == ride.id)
            )

            gps_track = WKTElement(wktutils.linestring_wkt(lonlat_points))

            ride_track = RideTrack()
            ride_track.gps_track = gps_track
            ride_track.ride_id = ride.id
            ride_track.elevation_stream = streams_dict["altitude"].data
            ride_track.time_stream = streams_dict["time"].data
            session.add(ride_track)

            # Some rides don't have start and end geo, but do have ride tracks from which we can infer the
            # start and end from which we can retrieve the weather.
            if not session.get(RideGeo, ride.id):
                ride_geo = RideGeo()
                ride_geo.ride_id = ride.id
                ride_geo.start_geo = WKTElement(
                    wktutils.point_wkt(lonlat_points[0][0], lonlat_points[0][1])
                )
                ride_geo.end_geo = WKTElement(
                    wktutils.point_wkt(lonlat_points[-1][0], lonlat_points[-1][1])
                )
                session.merge(ride_geo)

            ride.track_fetched = True
