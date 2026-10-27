"""Error types. Messages carry fixed codes and field names only, never raw input values."""


class CoreError(Exception):
    exit_code = 1

    def __init__(self, code, field=None, detail=None):
        self.code = code
        self.field = field
        self.detail = detail          # only values derived from the session list (e.g. a session date), never raw input
        super().__init__(code if field is None else "%s:%s" % (code, field))


class InputError(CoreError):
    """Invalid or insufficient input (data error). Never downgraded to 'condition not met'."""


class ConflictError(CoreError):
    """Conflicting decision records. Existing state must stay unchanged."""
