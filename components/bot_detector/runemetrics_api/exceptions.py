class UnexpectedRedirection(Exception):
    pass


class Undefined(Exception):
    pass


class RateLimitExceeded(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)
