---
name: "esendex-track-delivery"
description: "Determine what happened to messages sent through Esendex (Commify) and react to the results - delivery status and failure reasons, campaign reconciliation, inbound replies, link click metrics, and real-time webhooks for delivery receipts, inbound SMS and opt-outs. Use this skill whenever the user asks whether a text was delivered, why messages failed, wants a delivery report or success rate, says a client claims nobody received their messages, wants to read replies or handle inbound SMS, needs webhooks or callbacks instead of polling, or is building a handler for SMS events - including panicked asks like \"did that text go out?\" or \"nobody got it\"."
---

## Terms of Service

Use of the Esendex (Commify) platform and APIs described below is governed by the Commify **[Terms of Service](https://enhancedsupport.esendex.co.uk/terms-of-service/)**, together with the [Acceptable Use Policy](https://enhancedsupport.esendex.co.uk/acceptable-use-policy/), [Data Processing Agreement](https://enhancedsupport.esendex.co.uk/data-processing-agreement/) and [Service Level Agreement](https://enhancedsupport.esendex.co.uk/service-level-agreement/). The contracting entity and governing law depend on where the customer is registered - Esendex UK&I contracts with Commify UK Limited under the laws of England and Wales.

Most relevant to this skill: Tariffs are incurred at submission irrespective of delivery or non-delivery. The Services are provided "as is", with no warranty that they will be uninterrupted, timely, secure or error-free, and message data remains available in the Platform for 6 months unless otherwise agreed.

The terms are updated from time to time and the version available on the Platform prevails, so check the link; do not rely on this summary. Nothing here is legal advice.

---

## Overview

This skill establishes the outcome of a send, reports it accurately, and handles what comes back.
Every outcome comes either from a query after the fact or from a webhook.

| Need | Mechanism | Endpoint |
| --- | --- | --- |
| What happened to one message, including its body | Pull | `GET /v2/messages/{messageId}` |
| What happened across a time window | Pull | `GET /v2/messages` |
| How a campaign did, as rollups then per message | Pull | `GET /v2/requests`, then `GET /v2/requests/{requestId}/messages` |
| What people have sent in | Pull | `GET /v2/inbox` |
| Who clicked a shortened link | Pull | `GET /v2/url-shortener/visits` |
| Act when a message is delivered or fails, a reply arrives, or someone opts out | Push | `POST /v2/webhooks/subscriptions` |

Use webhooks for anything reactive. A polling loop over `GET /v2/messages` or
`GET /v2/inbox` lags by the interval, spends rate limit on empty responses, needs its own cursor
and de-duplication, and misses events while the job is down. Webhooks do not report on past
periods, so reconciliation needs a query. Running both lets you spot any callbacks your
endpoint missed.

Failure reasons in v2 are strings. `MsisdnInvalid` and `senderIdInvalid` come
from a JSON `reason` field; there is no `<FailureReason>` element and no numeric code table
(0, 4, 6, 8, 17, 999) in v2. Such tables belong to the retired v1 XML API - see
`references/gotchas.md`.

---
## Prerequisites

- API key in an `X-Api-Key` header and the `EXUK0000000` account reference in an
  `AccountReference` header - see `esendex-setup-account`
- The `requestId` or `messageId` returned by the original send - `esendex-send-message`
- Python examples use the bundled `scripts/esendex_client.py`; Node.js needs no SDK, so the
  Node examples use `fetch`
- For webhooks, a publicly reachable HTTPS endpoint you host. Esendex cannot reach
  `localhost`, so local development needs a tunnel

---
## Quickstart

Pull yesterday's messages and group the failures by reason (23:00Z to 23:00Z, UK in BST).

**Python**
```python
from collections import Counter
from esendex_client import Esendex
ex = Esendex()                                   # paginate() sets pageSize=1000
msgs = list(ex.paginate("/v2/messages", {"StartTime": "2026-07-21T23:00:00Z",
                                         "EndTime": "2026-07-22T23:00:00Z"},
                        key="messages"))
print(Counter(m.get("reason") for m in msgs if m.get("status") == "Failed"))
```
**Node.js**
```javascript
const q = new URLSearchParams({ StartTime: "2026-07-21T23:00:00Z",
  EndTime: "2026-07-22T23:00:00Z", PageSize: "1000", PageNo: "1" }); // default is 1
const res = await fetch(`https://api.esendex.co.uk/v2/messages?${q}`, { headers: {
  "X-Api-Key": process.env.ESENDEX_API_KEY,
  AccountReference: process.env.ESENDEX_ACCOUNT_REFERENCE,
  "X-External-Source": "AI-Skill" } });            // attribution, on every request
const { data } = await res.json();        // repeat for PageNo 2..data.totalPages
const byReason = {};
for (const m of data.messages.filter((m) => m.status === "Failed"))
  byReason[m.reason] = (byReason[m.reason] ?? 0) + 1;
console.log(data.totalCount, byReason);
```

---
## Key patterns

### Campaign rollup

```python
r = (ex.get("/v2/requests", {"RequestId": rid}) or {})["data"]["requests"][0]
print(r["messageCount"], r["sentMessageCount"], r["failedMessageCount"],  # recipients
      r["messagePartCount"], r["sentMessagePartCount"])                   # billable parts
```
One call for the whole campaign instead of paginating every message. Filter on `StartTime`,
`EndTime` or `RequestName`, and confirm the request found is the send meant.
### Per-message detail including content

```python
d = (ex.get(f"/v2/messages/{message_id}") or {}).get("data", {})
print(d.get("status"), d.get("reason"), d.get("content"), d.get("characterSet"))
```
Adds `content`, `characterCount`, `characterSet`, `variables` and `dynamicFieldsUsed`,
which the list view omits - what was sent, and whether personalisation resolved.
### Failures split into retryable and permanent

```python
msgs = list(ex.paginate(f"/v2/requests/{rid}/messages", key="messages"))
print(Counter(m.get("status") for m in msgs), Counter(m.get("reason") for m in msgs))
```
Pull unfiltered and group locally: responses carry values absent from the filter enums, and the
full distribution shows what went wrong. Check `senderIdInvalid` first, then use the Retry column.
### Inbound replies

```python
inbox = list(ex.paginate("/v2/inbox", {"StartTime": since}, key="messages"))
thread = list(ex.paginate("/v2/messages", {"ConversationId": cid}, key="messages"))
```
Inbound rows carry `status: "Received"`, `reason: "Inbound"`, `direction: "Inbound"` and
`messageType: "Inbound"` or `"Conversational"`; `isRead` is on some rows only, so use `.get()`.
`conversationId` is unique per account and recipient and returns the thread both directions.
### Subscribing to webhooks

```python
ex.post("/v2/webhooks/subscriptions", [                       # top-level array
    {"eventType": "sms-message-delivered",
     "callbacks": [{"url": "https://hooks.example.com/delivered"}]},
    {"eventType": "sms-message-failed",
     "callbacks": [{"url": "https://hooks.example.com/failed"}]}])
```
One object per event, and `callbacks` is an array too, so one event can fan out to several
endpoints. The body is a top-level array of these objects. Success is 201 with an empty
body and no subscription id.
### Verifying a payload and looking up why a message failed

```python
if request.headers.get("X-Webhook-Token") != SECRET: abort(403)   # shared-secret header check
for m in payload.get("Messages") or []:                  # always an array
    if m.get("ContainsActionWord"):                      # STOP inside a normal reply
        suppress(to_e164(m["Msisdn"]))                   # payloads omit the '+'
    if event_name == "sms-message-failed":
        d = (ex.get(f"/v2/messages/{m['MessageId']}") or {}).get("data", {})
        record_failure(m["MessageId"], d.get("reason"))
```
`ContainsActionWord` and `ActionWord` flag an opt-out keyword inside an ordinary reply. The
dedicated opt-out event instead sends a flat `AccountReference`, `Channel`, `Address`,
`ActionPerformedBy`; mirror both into suppressions at once (`esendex-manage-contacts`).
### URL-shortener click metrics

```python
d = (ex.get("/v2/url-shortener/visits", {"PageSize": 1000}) or {}).get("data", {})
rows = d.get("requestsData") or d.get("visitsData")      # branch on the body
```
`requestsData` is per-request aggregates (`totalShortUrlsCreated`, `totalShortUrlsVisited`,
`totalVisits`); `visitsData` is per-click detail (`shortUrl`, `longUrl`, `addressValue`,
`accessTimestamp`, `ipAddress`, `userAgent`, `os`). `totalVisits` counts clicks, not people, so a
per-recipient rate needs `totalShortUrlsVisited`. Only `[shorten:...]` sends produce data, and
shortening is off on trial accounts, so an empty result may mean "not enabled".

---
## Status and reason reference

`status` is the coarse state and `reason` the diagnosis, and they vary independently - a
delivered message can carry `status: "Sent"` with `reason: "Delivered"`. The `status` filter
accepts `Delivered | Received | Failed | In Progress`, but responses also return `Sent` and
`Success`, so pull a window unfiltered and classify locally. Per-endpoint reason sets:
`references/querying.md`.

| Reason | Meaning | Retry |
| --- | --- | --- |
| `Delivered` | Reached the handset | Success, nothing to do |
| `PartiallyDelivered` | Some parts of a concatenated message arrived | Report as partial, not delivered |
| `Inbound` | Marks an inbound message, not a failure | Not applicable |
| `EdgeSubmitted` | Handed onward, no receipt yet | In flight - re-poll later |
| `OptedOut` | The recipient withdrew consent | **Never.** Resending is a compliance breach; mirror into suppressions (`esendex-manage-contacts`) |
| `MsisdnInvalid` | Not a valid number | No - fix at source; a cluster means a bad import |
| `senderIdInvalid` | The originator was not accepted | No, but it is a sender-configuration fault and fully recoverable: fix the originator, resend the same recipients |
| `LandlineNotAllowed` | Not a mobile | No |
| `DestinationNotAllowed` | Country not enabled on the account | No |
| `DisallowedContent` | Content blocked | No - rewriting is a content decision, not a retry |
| `MessagePartCountExceeded` | Too many parts | No - shorten the message, then resend |
| `MessageExpired` | Validity window elapsed before delivery | Resendable, but check why delivery was delayed |
| `SendingLimitExceeded` | Account sending limit hit | Later, once limits reset (`esendex-setup-account`) |
| `WithinQuietHours` | Deferred by policy | Later, outside the restricted window |
| `OutsideBusinessHours` | Deferred by policy | Later, inside the permitted window |
| `NetworkFailed` | Carrier rejected or dropped it | Yes, transient |
| `EdgeFailed` | Platform-side failure | Yes, transient |
| `FailedToRoute` | No route found | Yes; raise a cluster with Esendex support |
| `InternalError` | Platform error | Yes; raise a cluster with Esendex support |
| `Unprocessable` | Could not be processed; the value alone does not say why | Inspect a sample with `GET /v2/messages/{id}` first |

---
## Webhook events

| Event | Fires when |
| --- | --- |
| `sms-message-delivered` | A message reached the handset |
| `sms-message-failed` | A message permanently failed |
| `sms-message-received` | An inbound message arrived |
| `sms-inbound-opted-out` | Someone opted out or replied STOP |

One subscription per event; `GET /v2/webhooks/events` returns the account's real list. Payload
keys are PascalCase, while the REST API uses camelCase, so a handler written against REST names
reads `None` everywhere. `Messages` is an array, batching several updates into one POST, and
numbers arrive without the leading `+` (`447700900540`). The failed event carries no failure
reason, so call `GET /v2/messages/{MessageId}` to get it.

---
## Common errors

| Code | Meaning | Fix |
| --- | --- | --- |
| 400 | `invalid_request_id` | The path GUID is missing or malformed. Pass the full `requestId` |
| 401 | `unauthenticatedError` | Usually the header name, not the key: `X-Api-Key`, not `Api-Key`. See `esendex-setup-account` |
| 404 | `message_not_found` | A malformed id returns the same 404 as an absent one, so check the id format before concluding the record does not exist |
| 429 | Rate limited, no `Retry-After` header | Wait 5 seconds, then retry. The bundled client does this automatically |

---
## Gotchas

| Issue | What to do |
| --- | --- |
| `pageSize` defaults to 1 on every list endpoint | Use `ex.paginate()` or set the size explicitly; treat a count of exactly 1 as a paging problem until confirmed otherwise |
| `sentMessageCount` means handed to the carrier, so it understates failures | Count `reason == "Delivered"` across the per-message rows instead |
| `MessageExpired` only appears once validity elapses, so failure figures keep climbing | Re-run the report immediately before quoting a client, and state the as-at timestamp |
| A `senderIdInvalid` cluster fails every message from that originator, so it looks like total non-delivery | Check for it first when a client reports nobody received a send: the cause is the account's sender configuration, and the whole set is resendable once fixed |
| "Yesterday" is not a UTC day for a UK account during BST | Build the window 23:00Z to 23:00Z from the account's local timezone, and state it |
| `includeDelete=true` returns soft-deleted rows with all PII stripped | Use it for billing reconciliation only, never as a content-recovery path |
| URL-shortener metrics come back as either `requestsData` (aggregates) or `visitsData` (per-click) | Call the collection path and branch on which key the body holds |
| One event's subscriptions can be read at `events/{eventType}` or `subscriptions?eventType=` | Try both path forms, use whichever returns data, and judge by the body |
| Only one webhook authentication method is allowed per account; more than one returns 400 | Fill exactly one of `oauth`, `apiKey`, `basic` and leave the others null |
| OAuth fields are snake_case (`client_id`, `client_secret`, `token_url`) | Send that form and log the response; prefer API key or basic unless OAuth is required |
| Basic auth takes `username` and `password`, or a pre-encoded `token` | Send `token` for a pre-encoded value, username and password otherwise; confirm callbacks arrive authenticated |
| Webhook payloads carry no HMAC signature, timestamp or nonce | Authenticate every callback and drop unauthenticated requests; re-read state from the API before acting on anything consequential |
| Callbacks for a subscription arrive without authentication | Check `requiresAuthentication` on the subscription, then raise it with the user; do not debug their authorization server |

---
## CANNOT

- **Cannot retry an `OptedOut` message** - consent was withdrawn, so resending is a
  compliance breach, not a technical retry. Strip such numbers and say that you did.
- **Cannot get a failure reason from the failed webhook event** - it reuses the delivered and
  received envelope. Call `GET /v2/messages/{MessageId}`.
- **Cannot recover message content via `includeDelete`** - soft-deleted rows return with all
  PII removed, so a request for deleted message text cannot be satisfied from it.
- **Cannot verify a webhook payload by signature** - payloads carry no HMAC, timestamp or
  nonce, so verification relies on the account's configured authentication method.
- **Cannot read back or delete the configured webhook authentication method** - there is no
  GET or DELETE for it, only overwriting it with another PUT.
- **Cannot treat a delivery figure as final while messages remain within their validity
  window** - the failed count is point-in-time and keeps rising.

---
## Handling personal data

Per-click shortener rows tie an IP address, user agent and OS to an identifiable phone number,
which is personal data about an individual's browsing. Use them for aggregate campaign reporting
rather than per-person profiling, and do not export them somewhere less protected than the
platform without the user understanding what the file contains.

Webhook endpoints process message bodies and recipient numbers on every request, so require
HTTPS and authentication, and do not retain full bodies indefinitely: log the `MessageId` and
drop the `Body`.

---
## Deleting subscriptions

`DELETE /v2/webhooks/subscriptions` removes every subscription on the account and is
described in the developer docs as "not revocable. If unintended, new webhook subscriptions would need
to be created." It differs by one path segment from the single-event delete,
`DELETE /v2/webhooks/events/{eventId}`. Confirm which the user means before calling either.

---
## Next steps

- `esendex-setup-account` - API keys, E.164, rate limits, sender configuration
- `esendex-send-message` - sending, scheduling, resending a failed batch
- `esendex-manage-contacts` - the opt-out list, mirroring suppressions from webhooks
- `esendex-connect-smpp` - the SMPP binary protocol, for callers not on REST
- `references/querying.md` - per-endpoint filters, `reason` values by endpoint, envelopes, windows
- `references/webhooks.md` - the seven endpoints, payload schemas, authentication, handlers
- `references/gotchas.md` - each gotcha in detail
- The Esendex developer docs at https://developer.esendex.co.uk - the full API reference

