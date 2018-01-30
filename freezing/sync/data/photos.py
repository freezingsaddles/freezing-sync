from instagram import InstagramAPIError
from sqlalchemy import and_

from freezing.model import meta, orm
# from freezing.web.utils.insta import configured_instagram_client, photo_cache_path
from freezing.model.orm import RidePhoto
from freezing.sync.data import StravaClientForAthlete

from . import BaseSync


class PhotoSync(BaseSync):

    name = 'sync-photos'
    description = 'Sync (non-primary) ride photos.'

    def sync_photos(self):
        sess = meta.scoped_session()

        q = sess.query(orm.Ride)
        q = q.filter_by(photos_fetched=False, private=False)

        for ride in q:
            self.logger.info("Writing out photos for {0!r}".format(ride))
            client = StravaClientForAthlete(ride.athlete)
            try:

                activity_photos = client.get_activity_photos(ride.id, only_instagram=True)
                """ :type: list[stravalib.orm.ActivityPhoto] """
                self.write_ride_photos_nonprimary(activity_photos, ride)

                sess.commit()
            except:
                sess.rollback()
                self.logger.exception("Error fetching/writing non-primary photos activity {0}, athlete {1}".format(ride.id, ride.athlete))

    def write_ride_photos_nonprimary(self, activity_photos, ride):
        """
        Writes out non-primary photos (currently only instagram) associated with a ride to the database.

        :param activity_photos: Photos for an activity.
        :type activity_photos: list[stravalib.orm.ActivityPhoto]

        :param ride: The db model object for ride.
        :type ride: bafs.orm.Ride
        """
        # [{u'activity_id': 414980300,
        #   u'activity_name': u'Pimmit Run CX',
        #   u'caption': u'Pimmit Run cx',
        #   u'created_at': u'2015-10-17T20:51:02Z',
        #   u'created_at_local': u'2015-10-17T16:51:02Z',
        #   u'id': 106409096,
        #   u'ref': u'https://instagram.com/p/88qaqZvrBI/',
        #   u'resource_state': 2,
        #   u'sizes': {u'0': [150, 150]},
        #   u'source': 2,
        #   u'type': u'InstagramPhoto',
        #   u'uid': u'1097938959360503880_297644011',
        #   u'unique_id': None,
        #   u'uploaded_at': u'2015-10-17T17:55:45Z',
        #   u'urls': {u'0': u'https://instagram.com/p/88qaqZvrBI/media?size=t'}}]

        raise NotImplementedError("This needs to be sorted out.")

        meta.engine.execute(RidePhoto.__table__.delete().where(and_(RidePhoto.ride_id == ride.id,
                                                                    RidePhoto.primary == False)))

        #insta_client = insta.configured_instagram_client()

        for activity_photo in activity_photos:

            # If it's already in the db, then skip it.
            existing = meta.scoped_session().query(RidePhoto).get(activity_photo.uid)
            if existing:
                self.logger.info("Skipping photo {} because it's already in database: {}".format(activity_photo, existing))
                continue

            try:
                media = insta_client.media(activity_photo.uid)

                photo = RidePhoto(id=activity_photo.uid,
                                  ride_id=ride.id,
                                  ref=activity_photo.ref,
                                  caption=activity_photo.caption)

                photo.img_l = media.get_standard_resolution_url()
                photo.img_t = media.get_thumbnail_url()

                meta.scoped_session().add(photo)

                self.logger.debug("Writing (non-primary) ride photo: {p_id}: {photo!r}".format(p_id=photo.id, photo=photo))

                meta.scoped_session().flush()
            except (InstagramAPIError, InstagramClientError) as e:
                if e.status_code == 400:
                    self.logger.warning("Skipping photo {0} for ride {1}; user is set to private".format(activity_photo, ride))
                elif e.status_code == 404:
                    self.logger.warning("Skipping photo {0} for ride {1}; not found".format(activity_photo, ride))
                else:
                    self.logger.exception("Error fetching instagram photo {0} (skipping)".format(activity_photo))

        ride.photos_fetched = True