class NoTeamsError(RuntimeError):
    """
    Raised when no teams are found.
    """
    pass


class MultipleTeamsError(RuntimeError):
    """
    Raised when multiple teams are found.
    """
    def __init__(self, teams):
        self.teams = teams


class ConfigurationError(RuntimeError):
    """
    Raised when there is a configuration error.
    """
    pass


class CommandError(RuntimeError):
    """
    Raised when there is a command error.
    """
    pass


class DataEntryError(ValueError):
    """
    Raised when there is a data entry error.
    """
    pass


class IneligibleActivity(ValueError):
    """
    Raised when an activity is ineligible.
    """
    pass


class ActivityNotFound(RuntimeError):
    """
    Raised when an activity is not found.
    """
    pass
