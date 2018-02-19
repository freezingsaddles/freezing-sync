
class NoTeamsError(RuntimeError):
    pass


class MultipleTeamsError(RuntimeError):
    def __init__(self, teams):
        self.teams = teams


class ConfigurationError(RuntimeError):
    pass


class CommandError(RuntimeError):
    pass


class DataEntryError(ValueError):
    pass


class IneligibleActivity(ValueError):
    pass


class ActivityNotFound(RuntimeError):
    pass