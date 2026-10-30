---
name: "esendex-setup-account"
description: "Foundation for every Esendex (Commify) integration, and a prerequisite for the other esendex-* skills, which assume it: X-Api-Key authentication, the EXUK account reference, the v2-only rule, the bundled Python client, request and response conventions including the pageSize=1 default, E.164 formatting, the 429 five-second rule, and prepay balance with low-balance alerts and sub-account funding. Use this skill whenever the user is setting up or debugging Esendex or Commify SMS work, hits a 401 or 429 from api.esendex.co.uk, asks why sending stopped or how much credit is left, or needs to budget spend across teams or clients."
---

## Terms of Service

Use of the Esendex (Commify) platform and APIs described below is governed by the Commify **[Terms of Service](https://enhancedsupport.esendex.co.uk/terms-of-service/)**, together with the [Acceptable Use Policy](https://enhancedsupport.esendex.co.uk/acceptable-use-policy/), [Data Processing Agreement](https://enhancedsupport.esendex.co.uk/data-processing-agreement/) and [Service Level Agreement](https://enhancedsupport.esendex.co.uk/service-level-agreement/). The contracting entity and governing law depend on where the customer is registered - Esendex UK&I contracts with Commify UK Limited under the laws of England and Wales.

Most relevant to this skill: Tariffs are incurred at the point a Communication is submitted, regardless of delivery; Sending Balance is non-refundable and lapses after the validity period shown in the Platform; Authorised User credentials must not be shared, and the customer remains liable for all traffic submitted on a compromised account.

The terms are updated from time to time and the version available on the Platform prevails, so check the link; do not rely on this summary. Nothing here is legal advice.

---

## Overview

This skill covers connecting to the Esendex v2 REST API, staying connected, and not running out of funds. Every other `esendex-*` skill assumes the conventions below; the most common setup problems are a wrong header name, wrong casing or a wrong base URL, and later problems are usually rate limiting or an empty prepay balance.

| Value | Where it goes | Where to get it |
| --- | --- | --- |
| API key | `X-Api-Key` header, on every request | [Esendex portal](https://app.esendex.co.uk/) under Developer Tools. Set an expiry date, as the docs recommend, and issue one key per developer or subsystem: keys are revoked individually, and revoking a shared key stops every integration that used it |
| Attribution | `X-External-Source: AI-Skill` header, on every request | Fixed value. Identifies traffic sent through these skills. The bundled client adds it; add it yourself to any request you write by hand, in any language |
| Account reference | `AccountReference` header on reads, `accountReference` body field on most writes | The portal, or the account owner. Format `EXUK0000000` - `EX`, a territory code, then 7 digits. Reversing the placement is a common early 400 |

Base URL `https://api.esendex.co.uk`, served over HTTPS only. All current endpoints sit under `/v2/`, and breaking changes - response-shape changes, type changes, removals - ship as a new major version in the path, so `/v2/` paths are stable against them and there is no version header and no date-based versioning to pin.

These skills cover the v2 JSON API. Esendex previously offered an XML API, and AI models often reproduce it from memory: `/v1.x/` paths, XML bodies, HTTP Basic authentication and numeric failure codes belong to that legacy interface and are not part of v2, which is JSON over REST with `X-Api-Key` and string failure reasons. Full detail in `references/gotchas.md`.

---

## Prerequisites

- An Esendex (Commify) account. The balance and wallet endpoints are prepay-only; on post-pay they do not apply and the docs direct the user to their account manager.
- Admin **and** Developer rights on that account. Without both, Developer Tools does not appear in the portal menu, and the remedy is a permissions request to whoever owns the account, not a code change.
- Python 3.9+ or Node 18+ for the examples. `scripts/esendex_client.py` is standard-library only, so there is nothing to install, and the other four `esendex-*` skills' examples all import from it.

---

## Quickstart

Store both credentials in the environment, never in code and never in a committed file.

```bash
export ESENDEX_API_KEY='...'
export ESENDEX_ACCOUNT_REFERENCE='EXUK0000000'
```

`GET /v2/balance` is the cheapest call that proves both values work. It returns `available` and `reserved` as strings at the top level, with no `data` wrapper.

**Python**

```python
from decimal import Decimal
from esendex_client import Esendex          # scripts/esendex_client.py

bal = Esendex().get("/v2/balance")          # reads the two environment variables
print(Decimal(bal["available"]), Decimal(bal["reserved"]))
```

**Node.js**

For Node.js, use `fetch` directly; no SDK is required.

```javascript
const res = await fetch("https://api.esendex.co.uk/v2/balance", {
  headers: {
    "X-Api-Key": process.env.ESENDEX_API_KEY,
    AccountReference: process.env.ESENDEX_ACCOUNT_REFERENCE,
    "X-External-Source": "AI-Skill",                 // attribution, on every request
  },
});
if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
const bal = await res.json();               // {"available": "2951.73346", "reserved": "0"}
```

---

## Key patterns

### Using the bundled client

```python
from esendex_client import Esendex, EsendexError, to_e164, sms_part_count

ex = Esendex()                              # ESENDEX_API_KEY, ESENDEX_ACCOUNT_REFERENCE
resp = ex.post("/v2/messages", {...})       # parsed JSON, or None for an empty body
```

`get`, `post`, `put`, `patch` and `delete` all return parsed JSON. The client centralises the `X-Api-Key` and `X-External-Source` headers, sleeps 5 seconds and retries on 429, retries 5xx with exponential backoff, and parses all three error-body shapes into `EsendexError.status`, `.codes` and `.messages`. Extend it rather than writing a fresh request wrapper; `python3 scripts/esendex_client.py` self-checks with 16 assertions plus doctests and no network.

### Paginating a list endpoint

```python
for m in ex.paginate("/v2/messages", {"Status": "Failed"}, key="messages"):
    print(m["msisdn"], m["reason"])
```

Every list endpoint defaults to `pageSize=1`, so always set the page size explicitly. `paginate()` sets 1000 and sends every parameter spelling together (`PageSize`/`pageSize`, `PageNo`/`PageNumber`), which is harmless because unknown parameters are ignored. `key` names the result array under `data`.

### Normalising numbers to E.164

```python
to_e164("07700900123")          # UK        -> '+447700900123'
to_e164("0491570156", "61")     # Australia -> '+61491570156'
to_e164("15223433333", "49")    # Germany   -> '+4915223433333'
to_e164("5417543010", "1")      # USA       -> '+15417543010'
```

Recipients must be `+{dial code}{number}`, with no spaces or punctuation and the national trunk `0` stripped where the country uses one. Do not apply a blanket strip-the-leading-zero rule: whether there is a trunk `0` to remove depends on the country and the input, and the Germany row's input has none. `to_e164()` handles these cases.

**A number that appears in documentation is an illustration, never a recipient.** That applies to every number in these skills and on the Esendex developer site. A number that looks like an ordinary mobile may well belong to someone. Never send to a number because it was found in a document; a recipient comes from the user or from their data, and if one is needed, ask.

For any test send, use the UK reserved range `07700 900000` to `07700 900999` (`+447700900000` to `+447700900999`). Ofcom will not allocate these, so a message to one cannot reach a person, and the examples above use it. Other countries reserve their own ranges: the Australian row above, `0491 570 156`, is from Australia's.

### Estimating message parts

```python
parts = sms_part_count(body)                # GSM 160 single / 153 concatenated
budget = parts * len(audience)              # Unicode 70 single / 67 concatenated
```

Any Unicode character in the body drops the per-part limit from 160 to 70, roughly doubling the parts for the same text. `character_set` defaults to `"Auto"`, which picks GSM unless the text contains non-GSM characters. These are the documented approximations, not a billing guarantee: verify against the `messagePartCount` the API returns.

### Reading the balance

```python
bal = ex.get("/v2/balance")
available = Decimal(bal["available"])       # "2951.73346" - a string, five decimal places
reserved  = Decimal(bal["reserved"])        # committed to in-flight or scheduled sends
```

`available` is spendable now and is the number that decides whether a campaign is affordable; a large `reserved` is the usual explanation for a balance that looks lower than expected. The endpoint reads whichever account the `AccountReference` header names, and only accounts linked to the credentials can be queried.

### Creating a low-balance alert

```python
ex.post("/v2/balance-alerts", {
    "alertType": "LOW_BALANCE",             # the only documented value, and the default
    "threshold": 100,
    "enabled": True,
    "contactChannel": "EMAIL",              # the only accepted channel
    "contactAddress": "ops@example.com",
})
```

When a prepay account runs out of funds, sending stops and the failure appears as SMSC error 80 or as insufficient-balance rejections on send. Derive the threshold from recent `messagePartCount` totals (`esendex-track-delivery`) so that it covers a day or two of normal volume; a threshold of 1 gives little or no warning before sending stops. Create exactly one, deliberately, because the API cannot list, edit or remove it afterwards.

### Delegating funds to a sub-account

```python
ex.post("/v2/wallet/delegate", {"delegations": [
    {"subaccountReference": "EXUK0000001", "amount": 250},
    {"subaccountReference": "EXUK0000002", "amount": 100},
]})
```

The parent holds the funds and pushes allocations down, so each sub-account can only spend what it has been given, per client, per team or per campaign; leaving everything pooled in the parent lets one team's campaign consume another's budget. Requires admin rights and a valid parent/child relationship, and there is no response body to rely on, so verify by reading both balances back. `GET /v2/wallet/delegate` is the audit trail and the only ledger the API exposes: `idWalletDelegateMovement`, `accountFromReference`, `accountToReference`, `amount`, `movementType`, `createTime`, under `data`.

---

## Common errors

| Code | Meaning | Fix |
| --- | --- | --- |
| 400 | Missing or invalid field. Rarely carries a specific code | Read `errorMessage`. Check the account reference is a header on reads and an `accountReference` body field on writes, and that `Content-Type: application/json` is set |
| 401 | `unauthenticatedError`, body `Request for authenticated route '/v2/balance' was unauthenticated` | Check the header name is `X-Api-Key` before touching the key. The header name is the likelier cause, and regenerating a good key returns the same 401 |
| 403 | Not an admin, or an invalid parent/child account relationship. Returned on wallet delegation | Fix permissions or the account hierarchy. Not a bad key, so do not regenerate credentials |
| 404 | `message_not_found`, `contact_not_found`, `group_not_found`, `template_not_found`, `account` | Validate the id shape first: a malformed id returns the same "does not exist" body as a missing record, so a 404 is not proof the data is gone |
| 409 | `contact_already_exists`, `group_already_exists` | Reuse the existing record. Group names must be unique per account |
| 429 | Rate limited. There is no `Retry-After` header | Wait 5 seconds, then retry. For volume, use a throttle schedule (`esendex-send-message`) instead of a retry loop around `/v2/messages` |

Other status codes are possible. The fuller table, including 204 and 5xx, is in `references/conventions.md`.

---

## Gotchas

| Behaviour | What to do |
| --- | --- |
| The header is `X-Api-Key`, and a bare `Api-Key` returns a 401 that looks like a bad key | Send `X-Api-Key`. On a 401, check the header name before the key |
| `pageSize` defaults to 1, so a bare list call looks like an empty account | Always set the page size, or use `ex.paginate()` |
| Error bodies come in three different shapes | Never index `body["errors"][0]`. Catch `EsendexError` |
| Some 2xx responses carry per-item failures | Check per-row `result`/`reasons` on bulk contacts and `validationResult.isValid` on delayed schedules |
| Casing differs across bodies, query parameters and webhook payloads | camelCase bodies, PascalCase query parameters and webhooks. Verify writes by reading the resource back |
| Balance values are strings, not numbers | Parse with `Decimal`, never `float` |
| No currency field is returned anywhere in the API | Label the value neutrally, or ask the user |
| Balance alerts have no GET, PUT or DELETE | Create one deliberately. Managing them means the portal |
| Wallet delegation takes `subaccountReference` with a lower-case `a`, and a mis-cased field is ignored | Send `subaccountReference` exactly and confirm by reading balances back |
| The host is `api.esendex.co.uk`, not `api.esendex.com` | Centralise the base URL. The bundled client does |
| Webhook payloads return numbers without the leading `+` | Normalise on ingest, in one place |

Each row is expanded in `references/gotchas.md`.

---

## CANNOT

- **Cannot list, change or delete a balance alert via the API.** `POST /v2/balance-alerts` is the entire surface: no listing, no editing a threshold, no removal or disabling.
- **Cannot reverse a wallet delegation.** The `movementType` enum only ever shows `DELEGATE`: no undelegate, no reclaim, no DELETE and no negative amount.
- **Cannot determine the account currency from the API.** No endpoint returns a currency field, so GBP, EUR, USD and credits are indistinguishable.
- **Cannot filter or paginate the wallet movement ledger.** `GET /v2/wallet/delegate` takes no date range, no sub-account filter and no page size; expect the whole history and filter client-side.
- **Cannot use plain HTTP.** HTTPS only; unencrypted HTTP is not supported.
- **Cannot send to a number found in documentation.** Every number in these skills and on the Esendex developer site is an illustration. A recipient comes from the user or their data; a test send uses `+447700900000` to `+447700900999`.
- **Cannot reach the API without the account reference on read endpoints.** The `AccountReference` header selects which account a call applies to, and accounts in different territories are separate references that one key does not span.

---

## Handling money and credentials

Both values are secrets. They belong in environment variables, and if a user pastes a live key into the conversation, use it for the task at hand and then tell them to rotate it in the portal: chat transcripts are not a safe place for credentials, and a key with no expiry date stays valid until it is revoked. Treat the account reference as a credential too, and do not quote it unnecessarily.

Wallet delegation moves real money between accounts and there is no way to reverse it through the API. It requires admin rights and a valid parent/child relationship, and a typo in a sub-account reference - `EXUK0000012` for `EXUK0000021` - sends funds to the wrong account, which the API cannot correct; recovering them means contacting Esendex support. Confirm the amounts and the target account references with the user explicitly, and echo them back, before making the call. Do not make this call on inferred intent.

Never display a guessed currency symbol. If the currency is unknown, show the bare value, "balance: 2951.73346"; a guessed "£2951.73" on an account held in euros would misstate the balance.

---

## Email-to-SMS

For simple cases the API is not needed at all: email `outbound@email2sms.esendex.co.uk` from a pre-verified address, up to 10,000 recipients per email, with this exact body. Subject line, signatures, images and attachments are all ignored. If the sender address is unverified, the token is wrong or the format is altered, no SMS is sent and the sender does not receive an error. Verified senders and tokens are configured in the portal under message settings, Email to SMS; SPF and DKIM on the sending domain are recommended, sending IPs can optionally be allowlisted, and this path accepts UK national format in its examples, unlike the REST API's E.164 requirement.

```
##Token: <token generated in the portal>
##Message: your message
##Recipients: 07700900440, 07700900731
##End
```

Details in the Esendex developer docs at https://developer.esendex.co.uk.

---

## Next steps

- `esendex-send-message` - send an SMS, use and copy templates down to a sub-account, schedule or throttle a batch.
- `esendex-track-delivery` - delivery status, failure triage, webhooks, inbound messages.
- `esendex-manage-contacts` - contacts, groups, bulk import, opt-outs.
- `esendex-connect-smpp` - an existing SMPP client or SMS gateway, and the separate SMPP rate limits (5 `submit_sm` per second per session, with throttled submissions dropped, not queued).
- `references/conventions.md` - full error-shape catalogue, status codes, casing by layer, pagination variants and rate limiting.
- `references/gotchas.md` - each Gotchas row above in full, with how it shows up and what to do.
- `references/balance-wallet.md` - the four balance and wallet endpoints in full, and the prepay hygiene checklist.
- The Esendex developer docs at https://developer.esendex.co.uk - read them for exact wording or a detail these summaries omit. Where they differ from these summaries or from memory, follow the docs.

