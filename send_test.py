#!/usr/bin/env python3
"""Send a single test SMS through the Esendex v2 API.

    export ESENDEX_API_KEY='...'
    export ESENDEX_ACCOUNT_REFERENCE='EXUK0000000'
    export ESENDEX_TEST_TO='07700900123'      # recipient; Ofcom drama range by default
    export ESENDEX_TEST_FROM='EsendexTest'      # alphanumeric sender id
    python3 send_test.py            # dry run - prints the payload, sends nothing
    python3 send_test.py --send     # actually sends

Needs esendex_client.py alongside it. Copy it from the source, e.g.
    cp src/esendex_client.py .
"""
import json
import os
import sys

from esendex_client import Esendex, to_e164, sms_part_count

# Never hardcode a real recipient: this file is committed. 07700900xxx is the Ofcom
# drama range, reserved for TV and radio drama and not allocated to subscribers,
# so a default run does not reach anyone.
TO = os.environ.get("ESENDEX_TEST_TO", "07700900123")
FROM = os.environ.get("ESENDEX_TEST_FROM", "EsendexTest")
TEXT = os.environ.get("ESENDEX_TEST_TEXT", "Hello")

# Characters documented as valid in an alphanumeric sender id. Space is not in the
# set, so check for spaces first if the API returns senderIdInvalid.
SENDER_CHARS = set(
    "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    "!\"#$%&'*+-./:<=>?@_"
)


def check_sender(sender: str) -> list[str]:
    return sorted({c for c in sender if c not in SENDER_CHARS})


def main() -> None:
    live = "--send" in sys.argv
    ex = Esendex()

    msisdn = to_e164(TO)          # raises ValueError rather than coercing a bad number
    parts = sms_part_count(TEXT)
    payload = {
        "accountReference": ex.account_reference,
        "channel": "SMS",
        "from": FROM,
        "name": "manual-test",
        "messageType": "InternalOperations",   # a manual test, not marketing
        "body": {"text": TEXT},
        "recipients": [{"msisdn": msisdn}],
    }

    print(f"to      {msisdn}  (from {TO})")
    print(f"from    {FROM!r}")
    print(f"text    {TEXT!r}")
    print(f"cost    {parts} part x 1 recipient = {parts} billable message")

    offenders = check_sender(FROM)
    if offenders:
        print(f"\nWARNING: sender {FROM!r} contains {offenders}, which is outside the")
        print("documented alphanumeric set. Expect senderIdInvalid. 'EsendexTest' avoids it.")
    print("NOTE: alphanumeric senders are one-way, so you cannot reply to this message.")

    print()
    print(json.dumps(payload, indent=2))

    if not live:
        print("\nDry run - nothing sent. Re-run with --send to actually send.")
        return

    resp = ex.post("/v2/messages", payload)
    data = resp["data"]
    # 202 Accepted means the message is queued, not yet delivered. Keep both ids;
    # they are what you use to look up delivery.
    print(f"\nqueued (202). requestId={data['requestId']} messageIds={data['messageIds']}")
    print("Confirm delivery via GET /v2/messages/{messageId} and read the `reason` field.")


if __name__ == "__main__":
    main()
