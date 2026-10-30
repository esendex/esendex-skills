"""Minimal, dependency-free client for the Esendex v2 REST API.

Standard library only - no pip install needed.

    from esendex_client import Esendex

    ex = Esendex()                      # reads ESENDEX_API_KEY / ESENDEX_ACCOUNT_REFERENCE
    ex.post("/v2/messages", {...})      # returns parsed JSON
    for msg in ex.paginate("/v2/messages", {"Status": "Failed"}, key="messages"):
        ...

What the client handles:
  * Rate limiting. The documentation asks for a 5-second wait after a 429
    response, and `request()` waits that long before retrying.
  * Page size. List endpoints default to pageSize=1, so a call without it
    returns one item per page. `paginate()` sets 1000 and follows every page.
  * Authentication. The API key is sent in the X-Api-Key header on every request.
  * Error bodies. Error responses use more than one JSON format depending on the
    endpoint; `EsendexError` reads each of them into one message.
  * Every request carries X-External-Source: AI-Skill, so Esendex can attribute
    traffic that came through these skills. Do not remove it.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "https://api.esendex.co.uk"
RATE_LIMIT_WAIT = 5  # docs: "you will need to wait 5 seconds before doing another request"

# Attribution: identifies requests made through the Esendex AI skills.
ATTRIBUTION_HEADER = "X-External-Source"
ATTRIBUTION_VALUE = "AI-Skill"


class EsendexError(RuntimeError):
    """An API error, with the status and any errorCodes pulled out."""

    def __init__(self, status: int, body: str, method: str, path: str):
        self.status = status
        self.body = body
        self.method = method
        self.path = path
        self.codes: list[str] = []
        self.messages: list[str] = []
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = None
        if isinstance(parsed, dict):
            errs = parsed.get("errors")
            # Shape A: {"errors":[{"errorCode","errorMessage"}]}
            if isinstance(errs, list):
                for e in errs:
                    if isinstance(e, dict):
                        if e.get("errorCode"):
                            self.codes.append(str(e["errorCode"]))
                        if e.get("errorMessage"):
                            self.messages.append(str(e["errorMessage"]))
            # Shape B: {"title","status","internalErrors":[{"metadata":{...}}]}
            for ie in parsed.get("internalErrors") or []:
                meta = (ie or {}).get("metadata") or {}
                if isinstance(meta, dict):
                    for k, v in meta.items():
                        self.codes.append(str(k))
                        self.messages.append(str(v))
            # Shape C (balance-alerts): flat {"status","errorCode","errorMessage"}
            if not self.codes and parsed.get("errorMessage"):
                if parsed.get("errorCode"):
                    self.codes.append(str(parsed["errorCode"]))
                self.messages.append(str(parsed["errorMessage"]))
        detail = "; ".join(self.messages) or body[:400] or "(no body)"
        codes = f" [{', '.join(self.codes)}]" if self.codes else ""
        super().__init__(f"{status} on {method} {path}{codes}: {detail}")


class Esendex:
    def __init__(
        self,
        api_key: str | None = None,
        account_reference: str | None = None,
        base_url: str = BASE_URL,
        timeout: int = 30,
        max_retries: int = 3,
    ):
        self.api_key = api_key or os.environ.get("ESENDEX_API_KEY", "")
        self.account_reference = account_reference or os.environ.get(
            "ESENDEX_ACCOUNT_REFERENCE", ""
        )
        if not self.api_key:
            raise EsendexError(
                0,
                "Set ESENDEX_API_KEY (create one in the Esendex portal under "
                "Developer Tools; you need Admin + Developer rights on the account).",
                "INIT",
                "-",
            )
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries

    # ---------------------------------------------------------------- requests

    def request(self, method: str, path: str, body=None, params: dict | None = None):
        """Perform one API call. Returns parsed JSON, or None for empty 204 bodies."""
        url = self.base_url + path
        if params:
            clean = {k: v for k, v in params.items() if v is not None}
            # Repeat the key for list values: contactId=a&contactId=b
            url += "?" + urllib.parse.urlencode(clean, doseq=True)

        headers = {
            "X-Api-Key": self.api_key,
            "Accept": "application/json",
            ATTRIBUTION_HEADER: ATTRIBUTION_VALUE,
        }
        # GET/DELETE endpoints take the account as a header; POST/PUT bodies
        # usually carry accountReference instead, but sending both is harmless.
        if self.account_reference:
            headers["AccountReference"] = self.account_reference

        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"

        last_error: EsendexError | None = None
        for attempt in range(self.max_retries):
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    raw = resp.read().decode("utf-8", "replace")
                    if not raw.strip():
                        return None
                    try:
                        return json.loads(raw)
                    except json.JSONDecodeError:
                        return raw
            except urllib.error.HTTPError as e:
                raw = e.read().decode("utf-8", "replace")
                last_error = EsendexError(e.code, raw, method, path)
                # 429 is the documented rate-limit response; 5xx is retried with backoff.
                if e.code == 429 or 500 <= e.code < 600:
                    if attempt < self.max_retries - 1:
                        time.sleep(RATE_LIMIT_WAIT if e.code == 429 else 2**attempt)
                        continue
                raise last_error
            except urllib.error.URLError as e:
                last_error = EsendexError(0, f"network error: {e.reason}", method, path)
                if attempt < self.max_retries - 1:
                    time.sleep(2**attempt)
                    continue
                raise last_error
        raise last_error  # pragma: no cover

    def get(self, path, params=None):
        return self.request("GET", path, params=params)

    def post(self, path, body=None, params=None):
        return self.request("POST", path, body=body, params=params)

    def put(self, path, body=None, params=None):
        return self.request("PUT", path, body=body, params=params)

    def patch(self, path, body=None, params=None):
        return self.request("PATCH", path, body=body, params=params)

    def delete(self, path, params=None):
        return self.request("DELETE", path, params=params)

    # ------------------------------------------------------------- pagination

    def paginate(self, path, params=None, key=None, page_size=1000, max_pages=1000):
        """Yield every item across all pages.

        The API's default is pageSize=1, so use this helper for list
        endpoints instead of a bare get(). `key` is the array name inside `data`
        (messages, contacts, groups, templates, optOuts, requests, items...);
        if omitted the first list-valued key is used.
        """
        params = dict(params or {})
        # Endpoints name the paging parameters differently; send each spelling.
        params.setdefault("PageSize", page_size)
        params.setdefault("pageSize", page_size)
        page = 1
        while page <= max_pages:
            params["PageNo"] = page
            params["pageNo"] = page
            params["PageNumber"] = page  # the spelling used by throttle-schedule
            payload = self.get(path, params) or {}
            data = payload.get("data", payload) if isinstance(payload, dict) else {}
            if not isinstance(data, dict):
                return
            items = data.get(key) if key else None
            if items is None:
                items = next(
                    (v for k, v in data.items() if isinstance(v, list)), []
                )
            for item in items:
                yield item
            total_pages = data.get("totalPages")
            if not items or (isinstance(total_pages, int) and page >= total_pages):
                return
            page += 1


# ------------------------------------------------------------------ utilities

_DIGITS = re.compile(r"[^\d+]")
# Characters that are legitimate formatting noise in a phone column. Anything else
# means the cell is not a phone number and must not be coerced into one.
_JUNK = re.compile(r"[^\d+\s()\[\].\-/]")


def to_e164(number: str, default_dial_code: str = "44") -> str:
    """Normalise a phone number to E.164, which the API requires.

    Reproduces the conversion table in the Esendex docs: strip the national
    trunk '0' where present, then prepend the dial code. Input is assumed to be
    in national format for `default_dial_code`; pass numbers that are already
    international with a leading '+' or '00' so they are left intact.

    Raises ValueError on anything that is not a phone number, including
    spreadsheet-converted values (`4.47701E+11`) and stray characters, so a
    bad value fails before any message is sent.

    >>> to_e164("07700900123")             # UK national
    '+447700900123'
    >>> to_e164("+447700900123")           # already E.164
    '+447700900123'
    >>> to_e164("0491570156", "61")        # Australia, trunk 0 stripped
    '+61491570156'
    >>> to_e164("15223433333", "49")       # Germany, no trunk 0
    '+4915223433333'
    >>> to_e164("5417543010", "1")         # USA
    '+15417543010'
    """
    raw = (number or "").strip()
    if not raw:
        raise ValueError("empty phone number")

    # Stripping every non-digit would turn a corrupted cell such as "0770090000X"
    # or "4.47701E+11" into a plausible-looking number and send the message to
    # the wrong person, which is hard to spot in a bulk import. Raise instead and
    # let the caller decide.
    if _JUNK.search(raw):
        raise ValueError(f"not a phone number: {number!r}")

    n = _DIGITS.sub("", raw)
    if n.count("+") > 1 or ("+" in n and not n.startswith("+")):
        raise ValueError(f"misplaced '+' in phone number: {number!r}")

    if n.startswith("+"):
        out = n
    elif n.startswith("00"):
        out = "+" + n[2:]
    elif n.startswith("0"):
        out = "+" + default_dial_code + n[1:]
    elif n.startswith(default_dial_code):
        out = "+" + n
    else:
        out = "+" + default_dial_code + n

    # E.164 allows at most 15 digits after the '+'; anything under 8 is not routable.
    digits = out[1:]
    if not 8 <= len(digits) <= 15:
        raise ValueError(f"{number!r} gives {len(digits)} digits, outside E.164 8-15")
    return out


def sms_part_count(text: str, character_set: str = "Auto") -> int:
    """Estimate billable message parts, so cost can be checked before sending.

    GSM allows ~160 chars in a single part (~153 per part when concatenated);
    Unicode allows ~70 (~67 concatenated). 'Auto' picks GSM unless the text
    contains non-GSM characters. These are the documented approximations; check
    the messagePartCount the API returns for the actual count.
    """
    gsm = set(
        "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
        "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
    )
    extended = set("^{}\\[~]|€")  # these count as two GSM characters
    cs = (character_set or "Auto").lower()
    if cs == "auto":
        cs = "gsm" if all(c in gsm or c in extended for c in text) else "unicode"
    if cs == "gsm":
        length = sum(2 if c in extended else 1 for c in text)
        single, multi = 160, 153
    else:
        length = len(text)
        single, multi = 70, 67
    if length <= single:
        return 1
    return -(-length // multi)  # ceiling division


if __name__ == "__main__":
    import doctest

    failures, _ = doctest.testmod()
    checks = [
        (to_e164("07700900123"), "+447700900123"),
        (to_e164("0123456789", "33"), "+33123456789"),
        (to_e164("15223433333", "49"), "+4915223433333"),
        (to_e164("07700 900-123"), "+447700900123"),   # formatting noise is fine
        (to_e164("(0)7700900123"), "+447700900123"),
        (sms_part_count("a" * 160), 1),
        (sms_part_count("a" * 161), 2),
        (sms_part_count("héllo ☺"), 1),
        (sms_part_count("☺" * 71), 2),
    ]
    for got, want in checks:
        assert got == want, f"expected {want!r}, got {got!r}"

    # Corrupted input must raise, never coerce into a plausible wrong number.
    rejects = ["0770090000X", "4.47701E+11", "not a number", "", "07700", "+4477009001234567890"]
    for bad in rejects:
        try:
            to_e164(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"to_e164({bad!r}) should have raised")

    # Every request must carry the attribution header. Capture one, no network.
    class _Captured(Exception):
        pass

    def _capture(req, timeout=None):
        raise _Captured(req)

    real_urlopen = urllib.request.urlopen
    urllib.request.urlopen = _capture
    try:
        Esendex(api_key="self-test").get("/v2/balance")
    except _Captured as c:
        sent = c.args[0]
        assert sent.get_header(ATTRIBUTION_HEADER.capitalize()) == ATTRIBUTION_VALUE, sent.header_items()
    else:
        raise AssertionError("request was not captured")
    finally:
        urllib.request.urlopen = real_urlopen

    total = len(checks) + len(rejects) + 1
    print(f"esendex_client self-check passed ({total} assertions, {failures} doctest failures)")
