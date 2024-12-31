import logging
from datetime import timedelta
from decimal import Decimal
from statistics import mean

from freezing.model import meta, orm
from sqlalchemy import text

from freezing.sync.config import config
from freezing.sync.data import BaseSync
from freezing.sync.utils.wktutils import parse_point_wkt
from freezing.sync.wx.visualcrossing.api import HistoVisualCrossing


# We only synchronize weather for yesterday's rides to avoid syncing early in the day and then having
# no (or forecasted) weather data for the rest of the day in our cache. This means our weather
# stats are always just up until yesterday. Shrug. We could do better. We also round lat/long
# to 1 decimal place which is about 10 miles which is terribly imprecise, but our current weather
# data is also very non hyperlocal and so this is just fine. We also only fetch weather data for
# the start day of the ride, so an epic century that starts just before midnight will receive no
# credit for the blizzard that starts at one minute past midnight.
class WeatherSync(BaseSync):
    """
    A class to synchronize weather data for rides.
    """

    name = "sync-weather"
    description = "Sync all ride weather"

    def sync_weather(
        self, clear: bool = False, limit: int = None, cache_only: bool = False
    ):
        """
        Synchronize weather data for rides.

        :param clear: Whether to clear existing weather data.
        :param limit: Limit the number of rides to process.
        :param cache_only: Whether to use only cached weather data.
        """
        sess = meta.scoped_session()

        if clear:
            self.logger.info("Clearing all weather data!")
            sess.query(orm.RideWeather).delete()

        if limit:
            self.logger.info("Fetching weather for first {0} rides".format(limit))
        else:
            self.logger.info("Fetching weather for all rides")

        # Find rides that have geo, but no weather
        sess.query(orm.RideWeather)
        q = text(
            """
            select R.id from rides R
            join ride_geo G on G.ride_id = R.id
            left join ride_weather W on W.ride_id = R.id
            where W.ride_id is null
            and date(R.start_date) < CURDATE() -- Only include rides from yesterday or before
            and time(R.start_date) != '00:00:00' -- Exclude bad entries.
            ;
            """
        )

        visual_crossing = HistoVisualCrossing(
            api_key=config.VISUAL_CROSSING_API_KEY,
            cache_dir=config.VISUAL_CROSSING_CACHE_DIR,
            cache_only=cache_only,
            logger=self.logger,
        )

        rows = meta.engine.execute(q).fetchall()  # @UndefinedVariable
        num_rides = len(rows)

        for i, r in enumerate(rows):
            if limit and i >= limit:
                logging.info("Limit ({0}) reached".format(limit))
                break

            ride = sess.query(orm.Ride).get(r["id"])
            self.logger.info(
                "Processing ride: {0} ({1}/{2})".format(ride.id, i, num_rides)
            )

            try:
                # If you can't reproduce the ancient infrastructure required by all this and so can't run any of the
                # geoalchemy stuff you can hardcode this to debug
                # start_geo_wkt = "POINT(-76.96 38.96)"
                start_geo_wkt = meta.scoped_session().scalar(ride.geo.start_geo.wkt)
                point = parse_point_wkt(start_geo_wkt)

                # We round lat/lon to decrease the granularity and allow better re-use of cache data.
                # Gives about an 80% hit rate vs about 20% for 2 decimals.
                lon = round(Decimal(point.lon), 1)
                lat = round(Decimal(point.lat), 1)

                self.logger.debug(
                    "Ride metadata: time={0} dur={1} loc={2}/{3}".format(
                        ride.start_date, ride.elapsed_time, lat, lon
                    )
                )

                hist = visual_crossing.histo_forecast(
                    time=ride.start_date, latitude=lat, longitude=lon
                )

                self.logger.debug("Got response in timezone {0}".format(hist.timezone))

                ride_start = ride.start_date.replace(tzinfo=hist.timezone)
                ride_end = ride_start + timedelta(seconds=ride.elapsed_time)

                # NOTE: if elapsed_time is significantly more than moving_time then we need to assume
                # that the rider wasn't actually riding for this entire time (and maybe just grab temps closest to start of
                # ride as opposed to averaging observations during ride.

                ride_observations = [
                    d for d in hist.day.hours if ride_start <= d.time <= ride_end
                ]

                start_obs = min(
                    hist.day.hours,
                    key=lambda d: abs((d.time - ride_start).total_seconds()),
                )
                end_obs = min(
                    hist.day.hours,
                    key=lambda d: abs((d.time - ride_end).total_seconds()),
                )

                if len(ride_observations) <= 2:
                    # if we don't have many observations, bookend the list with the start/end observations without double counting
                    ride_observations = (
                        [start_obs]
                        + [
                            o
                            for o in ride_observations
                            if o is not start_obs and o is not end_obs
                        ]
                        + [end_obs]
                    )

                for x in ride_observations:
                    self.logger.debug("Observation: {0}".format(x.__dict__))

                rw = orm.RideWeather()
                rw.ride_id = ride.id
                rw.ride_temp_start = start_obs.temperature
                rw.ride_temp_end = end_obs.temperature

                rw.ride_temp_avg = mean([o.temperature for o in ride_observations])

                rw.ride_windchill_start = start_obs.apparent_temperature
                rw.ride_windchill_end = end_obs.apparent_temperature
                rw.ride_windchill_avg = mean(
                    [o.apparent_temperature for o in ride_observations]
                )

                # scale the cumulative precipitation over the observation period by the fraction of time spent moving
                scale = (
                    ride.moving_time
                    / timedelta(hours=len(ride_observations)).total_seconds()
                )
                rw.ride_precip = (
                    sum([o.precip_accumulation for o in ride_observations]) * scale
                )
                rw.ride_rain = any([o.precip_type == "rain" for o in ride_observations])
                rw.ride_snow = any([o.precip_type == "snow" for o in ride_observations])

                rw.day_temp_min = hist.day.temperature_min
                rw.day_temp_max = hist.day.temperature_max

                rw.sunrise = hist.day.sunrise.time()
                rw.sunset = hist.day.sunset.time()

                self.logger.debug("Ride weather: {0}".format(rw.__dict__))

                sess.add(rw)
                sess.flush()

            except:
                self.logger.exception(
                    "Error getting weather data for ride: {0}".format(ride)
                )
                sess.rollback()

            else:
                sess.commit()
