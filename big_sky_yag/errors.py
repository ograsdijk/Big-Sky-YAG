class BigSkyYagError(RuntimeError):
    """Base exception for device communication and operation failures."""


class LaserTransportError(BigSkyYagError):
    """The serial transport did not provide a complete usable response."""


class LaserProtocolError(BigSkyYagError):
    """The controller returned a response that does not match its protocol."""


class LaserTransitionError(BigSkyYagError):
    """The laser did not reach a requested operational state."""
