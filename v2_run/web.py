"""The two HTTP calls of V2 and nothing else that opens a socket: the daily chart (Yahoo chart v8) of one symbol, and the posts
to one Discord webhook. urlopen is injected (the tests never open a socket to the outside). No exception text, URL or response
body leaves this module: a failed fetch is an exception that holds one fixed word, a failed post is one of three answers."""
import json
import socket
import urllib.error
import urllib.request

from v2_inputs import chart_url

USER_AGENT = "Mozilla/5.0 (compatible; soxl-alert-v2)"
FETCH_TIMEOUT = 30
SEND_TIMEOUT = 20
MAX_BYTES = 8 * 1024 * 1024
LIMIT = 1900                                   # Discord allows 2000 characters per message
PREVIEW_HEAD = "【SOXL日次・ローカルプレビュー（実送信なし）】"
LIVE_HEAD = "【詳細】"
WEBHOOK_PREFIXES = ("https://discord.com/api/webhooks/", "https://discordapp.com/api/webhooks/")
SENT, NOT_STARTED, UNKNOWN = "SENT", "NOT_STARTED", "UNKNOWN"
FETCH_WORDS = ("timeout", "url_error", "size", "other")      # and http_<3 digits> (the status that is not 200)


class FetchFailed(Exception):
    """A fetch that failed. The only argument is one fixed word (http_<status>, timeout, url_error, size, other)."""


def real_urlopen(request, timeout=None):
    """The real thing; the entry passes it on as the default of `urlopen`. The tests never reach it."""
    return urllib.request.urlopen(request, timeout=timeout)


def _status_word(status):
    return "http_%03d" % status if type(status) is int and 100 <= status <= 599 else "other"


def _word_of(error):
    """The fixed word for an exception of a fetch (the exception itself is never shown)."""
    if isinstance(error, urllib.error.HTTPError):
        return _status_word(error.code)
    if isinstance(error, TimeoutError):                    # socket.timeout is the same class from Python 3.10
        return "timeout"
    if isinstance(error, urllib.error.URLError):
        return "timeout" if isinstance(error.reason, TimeoutError) else "url_error"
    if isinstance(error, (ConnectionError, socket.gaierror)):
        return "url_error"
    return "other"


def make_fetch(urlopen=real_urlopen, failures=None):
    """fetch(symbol, start, end) -> bytes, for load_inputs. Any failure raises FetchFailed (load_inputs: the notice of the day
    is "input_market_fetch_failed"). A failed call first appends (symbol, word) to the list `failures` (N-05). No retry. The URL
    is chart_url's text as it is; nothing but the two headers and the timeout is passed to urlopen."""
    def fetch(symbol, start, end):
        request = urllib.request.Request(chart_url(symbol, start, end),
                                         headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        word, data = None, None
        try:
            with urlopen(request, timeout=FETCH_TIMEOUT) as response:
                status = getattr(response, "status", None)
                if status != 200:
                    word = _status_word(status)
                else:
                    data = response.read(MAX_BYTES + 1)
                    if type(data) is not bytes:
                        word = "other"
                    elif len(data) > MAX_BYTES:
                        word = "size"
        except Exception as error:                 # the type decides the word; the text is dropped
            word = _word_of(error)
            if isinstance(error, urllib.error.HTTPError):
                error.close()
        if word is not None:
            if failures is not None:
                failures.append((symbol, word))
            raise FetchFailed(word)
        return data
    return fetch


def live_text(text):
    """The text as it is really sent: the preview heading of the core becomes the live one (nothing else changes)."""
    return text.replace(PREVIEW_HEAD, LIVE_HEAD)


def split_text(text, limit=LIMIT):
    """The parts of a text of at most `limit` characters: the text itself when it is short; else it is cut at line ends (a line
    longer than the limit is cut where it must) and each part starts with "（n/N）" and a line feed. Joining the parts without
    those starts by line feeds gives the text again when no line was cut."""
    if len(text) <= limit:
        return [text]
    parts, cur = [], None
    for line in text.split("\n"):
        while len(line) > limit:
            if cur is not None:
                parts.append(cur)
                cur = None
            parts.append(line[:limit])
            line = line[limit:]
        if cur is None:
            cur = line
        elif len(cur) + 1 + len(line) > limit:
            parts.append(cur)
            cur = line
        else:
            cur = cur + "\n" + line
    if cur is not None:
        parts.append(cur)
    total = len(parts)
    return ["（%d/%d）\n%s" % (i + 1, total, part) for i, part in enumerate(parts)]


def _url_ok(url):
    return (type(url) is str and url.startswith(WEBHOOK_PREFIXES) and url.isascii() and url.isprintable()
            and " " not in url and "?" not in url)


class DiscordSender(object):
    """send(text) -> SENT / NOT_STARTED / UNKNOWN (the S4-B contract). One post per part, in order, `?wait=true`, `allowed_mentions`
    empty, no retry. NOT_STARTED only when no part can have been posted: a missing or malformed URL (also one that holds a `?`),
    or the first part refused with a 4xx, or no connection (name not resolved, connection refused). Every other failure, and any
    failure after the first part, is UNKNOWN. The URL is never shown (repr, errors, answers)."""

    def __init__(self, url, urlopen=real_urlopen):
        self._url = url if _url_ok(url) else None
        self._open = urlopen

    def __repr__(self):
        return "DiscordSender()"

    def _post(self, content):
        body = json.dumps({"content": content, "allowed_mentions": {"parse": []}}, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(self._url + "?wait=true", data=body, method="POST",
                                         headers={"Content-Type": "application/json", "User-Agent": USER_AGENT})
        answer = "unsure"
        try:
            with self._open(request, timeout=SEND_TIMEOUT) as response:
                status = getattr(response, "status", None)
                answer = "ok" if type(status) is int and 200 <= status < 300 else "unsure"
        except urllib.error.HTTPError as error:
            answer = "refused" if 400 <= error.code < 500 else "unsure"
            error.close()
        except urllib.error.URLError as error:
            answer = "refused" if isinstance(error.reason, (ConnectionRefusedError, socket.gaierror)) else "unsure"
        except (ConnectionRefusedError, socket.gaierror):
            answer = "refused"
        except Exception:
            answer = "unsure"
        return answer

    def send(self, text):
        if self._url is None or type(text) is not str:
            return NOT_STARTED
        for index, part in enumerate(split_text(live_text(text))):
            answer = self._post(part)
            if answer != "ok":
                return NOT_STARTED if (answer == "refused" and index == 0) else UNKNOWN
        return SENT


class DrySender(object):
    """The dry run: nothing leaves the runner; the text is kept for the run record. Answers SENT (the outbox of the dry run)."""

    def __init__(self):
        self.texts = []

    def __repr__(self):
        return "DrySender()"

    def send(self, text):
        self.texts.append(text)
        return SENT
