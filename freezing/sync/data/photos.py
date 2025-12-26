from freezing.model import meta, orm
from freezing.model.orm import Ride, RidePhoto
from sqlalchemy import and_
from stravalib.client import BatchedResultsIterator
from stravalib.model import ActivityPhoto

from freezing.sync.data import StravaClientForAthlete

from . import BaseSync

BigSize = 1000
SmallSize = 200


class PhotoSync(BaseSync):
    name = "sync-photos"
    description = "Sync (non-primary) ride photos."

    def sync_photos(
        self,
        athlete_id: int | None = None,
        activity_id: int | None = None,
        force: bool = False,
    ):
        with meta.transaction_context() as sess:
            q = sess.query(Ride)
            q = q.filter_by(private=False)
            if not force:
                q = q.filter_by(photos_fetched=False)
            if athlete_id:
                q = q.filter_by(athlete_id=athlete_id)
            if activity_id:
                q = q.filter_by(id=activity_id)

            for ride in q:
                self.logger.info("Writing out photos for {0!r}".format(ride))
                try:
                    client = StravaClientForAthlete(ride.athlete)
                    big_photos = client.get_activity_photos(ride.id, size=BigSize)
                    self.write_ride_photos_nonprimary(big_photos, ride)
                    small_photos = client.get_activity_photos(ride.id, size=SmallSize)
                    self.write_ride_photos_nonprimary(small_photos, ride)
                except:
                    self.logger.exception(
                        "Error fetching/writing "
                        "non-primary photos activity "
                        "{0}, athlete {1}".format(ride.id, ride.athlete),
                        exc_info=True,
                    )

    def write_ride_photos_nonprimary(
        self, activity_photos: BatchedResultsIterator[ActivityPhoto], ride: Ride
    ):
        """
        Writes out/updates all photos associated with a ride to the database.

        :param activity_photos: Photos for an activity.
        :type activity_photos: list[stravalib.orm.ActivityPhoto]

        :param ride: The db model object for ride.
        :type ride: bafs.orm.Ride
        """

        photos = meta.scoped_session().query(RidePhoto).filter_by(ride_id=ride.id)
        existing_photos = {photo.id: photo for photo in photos}

        for activity_photo in activity_photos:
            if not activity_photo.urls:
                self.logger.warning(
                    "Photo {} present, but has no URLs (skipping)".format(
                        activity_photo
                    )
                )
                continue

            # If it's already in the db, then skip it.
            photo = existing_photos.get(activity_photo.unique_id)
            if photo:
                del existing_photos[activity_photo.unique_id]
            else:
                self.logger.info(
                    "Adding photo {}: {}".format(
                        activity_photo.uid, activity_photo.caption
                    )
                )
                photo = RidePhoto(
                    id=activity_photo.unique_id,
                    ride_id=ride.id,
                    ref=activity_photo.ref,
                    primary=False,
                )
                meta.scoped_session().add(photo)

            photo.img_l = activity_photo.urls.get(str(BigSize)) or photo.img_l
            photo.img_t = activity_photo.urls.get(str(SmallSize)) or photo.img_t
            photo.caption = activity_photo.caption

            meta.scoped_session().flush()

        for deleted_photo in existing_photos.values():
            self.logger.info("Deleting deleted photo {}".format(deleted_photo))
            meta.scoped_session().delete(deleted_photo)

        ride.photos_fetched = True
