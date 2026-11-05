"""V2 S4-E (E-0), the entry of the morning run on the private repository's Actions: the commands morning, status, resend, init
and check-source, the HTTP of the market fetch and of the Discord webhook, and the facts of the chart responses. One place
decides everything once (R2-P01): the time, the Git of the checkout, the ref names of the mode, the store, the outbox, the sender
and the fetch. No private repository, workflow, secret, real fetch or real post exists in this stage. Draft, not adopted for
production."""
from .entry import MODES, REFUSED_JUDGMENT_EXISTS, SECRET_NAME, Setup, main
from .web import (FETCH_TIMEOUT, LIMIT, LIVE_HEAD, MAX_BYTES, PREVIEW_HEAD, SEND_TIMEOUT, USER_AGENT, WEBHOOK_PREFIXES,
                  DiscordSender, DrySender, live_text, make_fetch, split_text)

__all__ = ["DiscordSender", "DrySender", "FETCH_TIMEOUT", "LIMIT", "LIVE_HEAD", "MAX_BYTES", "MODES", "PREVIEW_HEAD",
           "REFUSED_JUDGMENT_EXISTS", "SECRET_NAME", "SEND_TIMEOUT", "Setup", "USER_AGENT", "WEBHOOK_PREFIXES", "live_text",
           "main", "make_fetch", "split_text"]
