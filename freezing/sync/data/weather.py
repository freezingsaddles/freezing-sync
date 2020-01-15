import logging
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import text

from freezing.model import meta, orm

from freezing.sync.utils.wktutils import parse_point_wkt
from freezing.sync.wx.sunrise import Sun

from darksky.api import DarkSky
from darksky.types import weather
from pytz import timezone

from freezing.sync.config import config

from freezing.sync.data import BaseSync


class WeatherSync(BaseSync):
    """
    Synchronize rides from data with the database.
    """

    name = 'sync-weather'
    description = 'Sync all ride weather'

    def sync_weather(self, clear:bool = False, limit: int = None, cache_only: bool = False):
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
        q = text("""
            select R.id from rides R
            join ride_geo G on G.ride_id = R.id
            left join ride_weather W on W.ride_id = R.id
            where W.ride_id is null
            and date(R.start_date) < CURDATE() -- Only include rides from yesterday 
            and time(R.start_date) != '00:00:00' -- Exclude bad entries.
            ;
            """)

        darksky = DarkSky(config.DARK_SKY_API_KEY)

        rows = meta.engine.execute(q).fetchall()  # @UndefinedVariable
        num_rides = len(rows)

        for i, r in enumerate(rows):

            if limit and i >= limit:
                logging.info("Limit ({0}) reached".format(limit))
                break

            ride = sess.query(orm.Ride).get(r['id'])
            self.logger.info("Processing ride: {0} ({1}/{2})".format(ride.id, i, num_rides))

            try:

                start_geo_wkt = meta.scoped_session().scalar(ride.geo.start_geo.wkt)
                point = parse_point_wkt(start_geo_wkt)

                # We round lat/lon to decrease the granularity and allow better re-use of cache data.
                lon = round(Decimal(point.lon), 3)  # go back to 1 digit precision if we need caching?
                lat = round(Decimal(point.lat), 3)  # go back to 1 digit precision if we need caching?

                self.logger.debug("Ride metadata: time={0} dur={1} loc={2}/{3}".format(ride.start_date, ride.elapsed_time, lat, lon))

                hist = darksky.get_time_machine_forecast(
                    time=ride.start_date,
                    latitude=lat,
                    longitude=lon,
                    exclude=[weather.MINUTELY, weather.ALERTS]  # minutely only gives precipitation
                )

                self.logger.debug("Got response in timezone {0}".format(hist.timezone))

                ride_start = ride.start_date.replace(tzinfo=timezone(hist.timezone))
                ride_end = ride_start + timedelta(seconds=ride.elapsed_time)

                # NOTE: if elapsed_time is significantly more than moving_time then we need to assume
                # that the rider wasn't actually riding for this entire time (and maybe just grab temps closest to start of
                # ride as opposed to averaging observations during ride.

                ride_observations = [d for d in hist.hourly.data if ride_start <= d.time <= ride_end]

                start_obs = min(hist.hourly.data, key=lambda d:abs((d.time - ride_start).total_seconds()))
                end_obs = min(hist.hourly.data, key=lambda d:abs((d.time - ride_end).total_seconds()))
                daily = hist.daily.data[0]

                def avg(l):
                    no_nulls = [e for e in l if e is not None]
                    if not no_nulls:
                        return None
                    return sum(no_nulls) / len(no_nulls) * 1.0  # to force float

                rw = orm.RideWeather()
                rw.ride_id = ride.id
                rw.ride_temp_start = start_obs.temperature
                rw.ride_temp_end = end_obs.temperature
                if len(ride_observations) <= 2:
                    # if we don't have many observations, bookend the list with the start/end observations without double counting
                    ride_observations = [start_obs] + [o for o in ride_observations if o is not start_obs and o is not end_obs] + [end_obs]

                rw.ride_temp_avg = avg([o.temperature for o in ride_observations])

                rw.ride_windchill_start = start_obs.apparent_temperature
                rw.ride_windchill_end = end_obs.apparent_temperature
                rw.ride_windchill_avg = avg([o.apparent_temperature for o in ride_observations])

                for x in ride_observations:
                    self.logger.debug("Observation: {0}".format(x.__dict__))

                # Sometimes attributes are None, sometimes they are AttributeError
                precip_type = lambda h: getattr(h, 'precip_type', None)
                precip_intensity = lambda h: getattr(h, 'precip_intensity', None) or 0

                # precipitation is a bit wonky. intensity is mm/hour, accumulation is never set. but it's something.
                rw.ride_precip = sum([precip_intensity(o) for o in ride_observations])
                rw.ride_rain = any([precip_type(o) == 'rain' for o in ride_observations])
                rw.ride_snow = any([precip_type(o) == 'snow' for o in ride_observations])

                rw.day_temp_min = daily.temperature_min
                rw.day_temp_max = daily.temperature_max

                self.logger.debug("Ride weather: {0}".format(rw.__dict__))

                # ride.weather_fetched = True  # (We don't have such an attribute, actually.)
                # (We get this from the activity now.)
                # ride.timezone = hist.date.tzinfo.zone

                sess.add(rw)
                sess.flush()

                if lat and lon:
                    try:
                        sun = Sun(lat=lat, lon=lon)
                        rw.sunrise = sun.sunrise(ride_start)
                        rw.sunset = sun.sunset(ride_start)
                    except:
                        self.logger.exception("Error getting sunrise/sunset for ride {0}".format(ride))
                        # But soldier on ...

            except:
                self.logger.exception("Error getting weather data for ride: {0}".format(ride))
                sess.rollback()

            else:
                sess.commit()
