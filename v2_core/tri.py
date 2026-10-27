"""Three-valued flag: UNKNOWN is never replaced by TRUE or FALSE."""
import enum


class Tri(enum.Enum):
    TRUE = "TRUE"
    FALSE = "FALSE"
    UNKNOWN = "UNKNOWN"


def from_bool(value):
    return Tri.TRUE if value else Tri.FALSE


def tri_and(*values):
    """FALSE if any FALSE; TRUE if all TRUE; otherwise UNKNOWN."""
    if any(v is Tri.FALSE for v in values):
        return Tri.FALSE
    if all(v is Tri.TRUE for v in values):
        return Tri.TRUE
    return Tri.UNKNOWN
