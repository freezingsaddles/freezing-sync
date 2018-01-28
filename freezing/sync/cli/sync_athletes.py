from freezing.model import meta, orm

from freezing.sync.data.athlete import AthleteSync

from . import BaseCommand


class SyncAthletesScript(BaseCommand):
    """
    Updates the athlete records, and associates with teams.

    (Designed to be run periodically to ensure that things like names and team
    membership are kept in sync w/ Strava.)
    """

    @property
    def description(self) -> str:
        return 'Sync all athletes.'

    @property
    def name(self):
        return 'sync-athletes'

    def execute(self, args):
        fetcher = AthleteSync(logger=self.logger)
        fetcher.sync_athletes()


def main():
    SyncAthletesScript().run()


if __name__ == '__main__':
    main()