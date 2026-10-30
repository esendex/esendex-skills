# Balance and wallet endpoints in full

Four endpoints, all prepay-only. On a post-pay account they do not apply and the
docs direct the user to their account manager instead.

| Operation | Call |
| --- | --- |
| Read balance | `GET /v2/balance` |
| Create a low-balance alert | `POST /v2/balance-alerts` |
| Delegate funds to sub-accounts | `POST /v2/wallet/delegate` |
| Audit delegations | `GET /v2/wallet/delegate` |

The last two share a path and differ only by method. The developer docs title them "Share" and "Get Movement".

## GET /v2/balance

Headers: `X-Api-Key`, `AccountReference`. No parameters, no body.

```python
from decimal import Decimal
from esendex_client import Esendex

ex = Esendex()
bal = ex.get("/v2/balance")
available = Decimal(bal["available"])
reserved = Decimal(bal["reserved"])
```

Response:

```json
{"available": "2951.73346", "reserved": "0"}
```

There is no `data` wrapper here, unlike most of the API. The two fields sit at the
top level.

The values are strings, not numbers: `"2951.73346"`, five decimal places, quoted.
Parse with `Decimal`, not `float`, for arithmetic on the value or comparison against
a threshold. Parsing the string directly avoids floating-point errors of the
`float("0.1") + float("0.2")` kind, since the API returns an exact decimal.

No currency field is returned, on this endpoint or anywhere else in the API. The response does not indicate whether the number is GBP, EUR, USD or credits.
Never render a currency symbol inferred from the `EXUK` prefix or from the user's
locale. Show the bare value, "balance: 2951.73346"; a guessed "£2951.73" on an
account held in euros would misstate the balance. If the user needs a symbol, ask them.

`available` is spendable now. `reserved` is committed
to sends that are in flight or scheduled but not yet billed. To assess whether a
campaign is affordable, `available` is the number that matters. A large `reserved`
is the usual explanation when a balance looks lower than the user expects: a large
scheduled or throttled batch is holding funds.

The endpoint reads whichever account the `AccountReference` header names, and only
accounts linked to the credentials in use can be queried. To check a sub-account's
balance, send that sub-account's reference in the header.

Documented errors: 400 (shape A), 401 `unauthenticatedError` (shape A).

## POST /v2/balance-alerts

Headers: `X-Api-Key`, `AccountReference`, `Content-Type: application/json`.

```python
ex.post("/v2/balance-alerts", {
    "alertType": "LOW_BALANCE",
    "threshold": 100,
    "enabled": True,
    "contactChannel": "EMAIL",
    "contactAddress": "ops@example.com",
})
```

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `threshold` | integer | yes | Balance at which the alert fires. Echoes back as a float (`1.0`) |
| `enabled` | boolean | yes | |
| `contactChannel` | string | yes | Only value is `EMAIL` |
| `contactAddress` | string | yes | A single recipient address |
| `alertType` | string | no | Only value is `LOW_BALANCE`, which is also the default if omitted. Send it explicitly anyway |

Response is 201 with the created object echoed back under `data`.

A prepay account that runs out of funds stops sending. The failure appears as SMSC
error 80 (insufficient balance, see `esendex-connect-smpp`) or as rejections on send,
which can be mistaken for a network fault. An alert gives warning before sending is
interrupted.

Base the threshold on recent spend. Sum recent `messagePartCount`
totals (`esendex-track-delivery`) to get a daily spend rate, and set the threshold
at a day or two of normal volume. A threshold of 1 gives
little or no warning before sending stops.

Tell the user about two limitations.

`contactAddress` takes one address. To alert several people, use a distribution-list
address.

There is no GET, PUT or DELETE for balance alerts. Creating them is the entire API
surface: they cannot be listed, a threshold cannot be changed, and an alert cannot
be disabled or removed. That makes them close to write-once, so avoid creating
multiple alerts during testing, since the API cannot list or remove them afterwards.
Manage or remove alerts in the portal, and create one deliberately with a
considered threshold.

Documented errors: 400 (shape C, flat), 401 `unauthenticatedError` (shape A).

## POST /v2/wallet/delegate

This moves real money between accounts. Read the whole section before calling it.

Headers: `X-Api-Key`, `AccountReference` (the parent), `Content-Type`.

```python
ex.post("/v2/wallet/delegate", {
    "delegations": [
        {"subaccountReference": "EXUK0000001", "amount": 250},
        {"subaccountReference": "EXUK0000002", "amount": 100},
    ],
})
```

`delegations` is an array, so several sub-accounts can be funded in one call.

| Field | Type | Notes |
| --- | --- | --- |
| `delegations[].subaccountReference` | String | The sub-account to receive funds. Note the casing, below |
| `delegations[].amount` | Integer | Amount of funds to delegate |

Casing: the field is `subaccountReference`, with a lower-case a. Unknown fields are
ignored, so a mis-cased `subAccountReference` may not be applied, and a 200 response
is not proof that funds moved. If a delegation appears to have had no effect, check
the casing first, and confirm by reading balances back.

Permissions, from the documented 403: the caller must be an admin and there must be
a valid parent/child relationship between the two accounts. A 403 here is therefore
a permissions or account-hierarchy problem, not a bad key, and regenerating
credentials will not fix it.

A successful delegation returns 200 OK with no response body. Verify a delegation landed by reading
`GET /v2/balance` back for both the parent and the sub-account.

There is no way to reverse a delegation through the API. The `movementType` enum on
the audit endpoint only ever shows `DELEGATE`: there is no undelegate, no reclaim, no
DELETE, and no negative amount. Together with the casing and the empty response
body, this makes delegation the highest-risk call these skills make: confirm before
calling and verify afterwards.

Before delegating on a user's behalf, confirm the amounts and the target account
references explicitly, and echo them back for confirmation. A typo in a sub-account
reference, `EXUK0000012` for `EXUK0000021`, sends funds to the wrong account, which
the API cannot correct; recovering them means contacting Esendex support. Do not make
this call on inferred intent.

Documented errors: 400, 401, 403, all shape A. Read `errorMessage`; do not branch
on a specific code.

## GET /v2/wallet/delegate

Headers: `X-Api-Key`, `AccountReference`. No parameters.

```python
movements = ex.get("/v2/wallet/delegate")["data"]
for m in movements:
    print(m["createTime"], m["accountFromReference"], "->",
          m["accountToReference"], m["amount"], m["movementType"])
```

```json
{"data": [{
  "idWalletDelegateMovement": 9007199254740991,
  "accountFromReference": "string",
  "accountToReference": "string",
  "amount": 0,
  "movementType": "DELEGATE",
  "createTime": "2025-09-24T15:42:26.457Z"
}]}
```

| Field | Notes |
| --- | --- |
| `idWalletDelegateMovement` | Numeric id. The sample value, 2^53-1, is a schema placeholder |
| `accountFromReference` | Source account |
| `accountToReference` | Destination account |
| `amount` | Numeric here, unlike the string balances on `/v2/balance` |
| `movementType` | Only `DELEGATE` |
| `createTime` | ISO 8601, UTC |

The endpoint takes no filter or pagination parameters: no date range, no
sub-account filter, no page size. On a busy account, expect the entire history in one response
and filter client-side; the response grows as the history does.

This is the only ledger the API exposes; it has no other per-account statement,
spend report or transaction endpoint. If the user needs an internal record
of allocations, poll this and store the rows.

A 404 with `errorCode: "account"` and message "A account with the given id does not
exist" means the account reference is wrong, either absent or malformed.

## Prepay hygiene setup

Offer this proactively for any high-volume integration:

1. Create one low-balance alert, at a threshold covering a couple of days of normal
   volume. Once, deliberately, because the API cannot edit or delete it later.
2. Check `available` before a large campaign. Estimate cost as
   `sms_part_count(body) * len(audience)`, remembering that any Unicode character
   in the body drops the per-part limit from 160 to 70 and so roughly doubles the
   parts for the same text.
3. With sub-accounts, delegate deliberately instead of leaving everything pooled in
   the parent, so one team's or client's campaign cannot consume another's budget.
4. Poll `GET /v2/wallet/delegate` if a record of allocations is needed, since
   nothing else exposes them.
