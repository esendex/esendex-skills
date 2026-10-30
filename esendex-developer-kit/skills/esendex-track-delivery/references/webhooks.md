# Webhooks - endpoints, payloads and authentication

Companion to `SKILL.md`.

## The seven endpoints

| Operation | Call | Success |
| --- | --- | --- |
| List events available to the account | `GET /v2/webhooks/events` | 200 |
| Get subscriptions for an event | `GET /v2/webhooks/events/{eventType}` | Judge by the body - see below |
| Create subscription(s) | `POST /v2/webhooks/subscriptions` | 201, empty body |
| Change callback URL(s) for an event | `PUT /v2/webhooks/events/{eventType}` | 204 |
| Delete one event's subscription | `DELETE /v2/webhooks/events/{eventId}` | 204 |
| Delete every subscription on the account | `DELETE /v2/webhooks/subscriptions` | 204 |
| Set the account's authentication method | `PUT /v2/webhooks/authentication-methods` | 201 |

Call `GET /v2/webhooks/events` and inspect the response to see what the account
offers. Send the `AccountReference` header on it, as on every other call.

The two delete endpoints differ by one path segment (`events/{eventId}` versus
`subscriptions`), and the one that removes everything is the shorter path. See
the warning below.

## Available events

| eventId | Fires when |
| --- | --- |
| `sms-message-delivered` | A message reached the handset |
| `sms-message-failed` | A message permanently failed |
| `sms-message-received` | An inbound message arrived |
| `sms-inbound-opted-out` | Someone opted out / replied STOP |

One subscription per event. The account's actual list may differ from the set
above, so call `GET /v2/webhooks/events` for it; do not assume.

## Creating subscriptions

Send a top-level array with one object per event, each carrying `eventType` and a
`callbacks` array of `url` objects:

```python
from esendex_client import Esendex

ex = Esendex()
ex.post("/v2/webhooks/subscriptions", [
    {"eventType": "sms-message-delivered",
     "callbacks": [{"url": "https://hooks.example.com/esendex/delivered"}]},
    {"eventType": "sms-message-failed",
     "callbacks": [{"url": "https://hooks.example.com/esendex/failed"}]},
    {"eventType": "sms-message-received",
     "callbacks": [{"url": "https://hooks.example.com/esendex/inbound"}]},
    {"eventType": "sms-inbound-opted-out",
     "callbacks": [{"url": "https://hooks.example.com/esendex/optout"}]},
])
```

Further optional fields are `platform` and `optionalNotes` (inside each callback),
and `requiresAuthentication` and `contactEmail` (on the subscription).
Set `requiresAuthentication` on subscriptions that should use the account
authentication method, log the result, and confirm callbacks arrive
authenticated.

`callbacks` is an array, so one event can fan out to several endpoints, which is
useful when a new consumer is being onboarded alongside an existing one.

Success is 201 with an empty body, so there is nothing to parse and no
subscription id returned. If a create fails, check the body shape and the account
reference first.

## Reading and updating subscriptions

The subscriptions for one event can be read with
`GET /v2/webhooks/events/{eventType}` or with
`GET /v2/webhooks/subscriptions?eventType={eventType}`. Try both path forms, use
whichever returns data, and judge the result by the body, not the status code:

```python
for attempt in (
    lambda: ex.get("/v2/webhooks/events/sms-message-delivered"),
    lambda: ex.get("/v2/webhooks/subscriptions", {"eventType": "sms-message-delivered"}),
):
    try:
        got = attempt()
    except Exception as e:
        print("failed:", e); continue
    if got:
        print(got); break
```

`PUT /v2/webhooks/events/{eventType}` takes a top-level array of callback
objects. Send the complete set of URLs required, then read the subscriptions back
to confirm whether the call replaced the existing set or added to it.

```python
ex.put("/v2/webhooks/events/sms-message-delivered",
       [{"url": "https://hooks.example.com/esendex/v2/delivered"}])
```

## Subscription deletion

`DELETE /v2/webhooks/subscriptions` removes every webhook subscription on the
account. The developer docs state: "This action is not revocable. If unintended, new
webhook subscriptions would need to be created." The call takes no confirmation
parameter, and there is no list-all-subscriptions endpoint for checking afterwards
what was removed.

To remove one event, use `DELETE /v2/webhooks/events/{eventId}`, one extra path
segment. The `eventId` values are the event names (`sms-message-delivered` etc.).

If a user says "remove the webhooks", ask whether they mean one event or all of
them before issuing anything, and say up front that the all-subscriptions form
can only be undone by recreating each subscription by hand.

## Payload shape

Keys are PascalCase. The REST API is camelCase. A handler written against the
REST field names will read `None` from every field and record empty values.

The delivered, failed and received events share one envelope:

```json
{
  "RequestId": "afe6beb6-6d92-4efa-bcb8-39164092f449",
  "AccountReference": "EXUK0000000",
  "Channel": "SMS",
  "Status": "Received",
  "Messages": [
    {
      "MessageId": "31b2dbc7-765e-4cb2-ac0f-a788cf0cbcf0",
      "MostRecentOutboundMessageId": null,
      "MostRecentOutboundRequestId": null,
      "OccurredAtTime": "2026-02-18T15:18:08.8212423Z",
      "Status": "Received",
      "DestinationCode": "",
      "Body": "Lorem ipsum dolor sit amet...",
      "MessageParts": 2,
      "MessageCoding": "GSM",
      "ContactId": null,
      "ConversationStatus": "Updated",
      "Originator": "447700900931",
      "Msisdn": "447700900540",
      "ContainsActionWord": false,
      "ActionWord": null,
      "Keyword": "",
      "SenderType": "VirtualMobileNumber"
    }
  ]
}
```

Field notes:

| Field | Notes |
| --- | --- |
| `Messages` | An **array**. One POST can batch several message updates. Loop it |
| `Msisdn` | The recipient (outbound) or sender (inbound), **without a leading `+`** |
| `Originator` | The other end of the pair, also without `+` |
| `Status` | Repeated at envelope and message level; `Received` in the sample, log the others you see |
| `MessageParts` | Billable parts, not characters |
| `MessageCoding` | `GSM` in the sample; expect other values |
| `ConversationStatus` | `Updated` in the sample; expect other values |
| `SenderType` | `VirtualMobileNumber` in the sample; expect other values |
| `ContainsActionWord` / `ActionWord` | Opt-out keyword detected inside an ordinary inbound message |
| `Keyword` | Empty string in the sample |
| `MostRecentOutboundMessageId` / `RequestId` | Null in the sample. May link a reply to the outbound message it answers; check whether it is populated before relying on it |
| `ContactId` | Links to a stored contact when one exists |
| `OccurredAtTime` | When the event happened, distinct from when you received it |

There is no failure-reason field. The failed event reuses this exact envelope, so
to learn why a message failed, call `GET /v2/messages/{MessageId}` and read
`reason`.

The opt-out event has its own flat shape with no `Messages` array at all:

```json
{ "AccountReference": "string", "Channel": "string", "Address": "string", "ActionPerformedBy": "string" }
```

`Address` is the number that opted out; expect the same no-plus format and
normalise. `ActionPerformedBy` may distinguish a recipient-initiated STOP from a
manual suppression by a user, which matters for audit. Log it to confirm which
values appear.

## Reference handler

```python
from esendex_client import to_e164

def handle(event_name, payload):
    if event_name == "sms-inbound-opted-out":
        suppress(to_e164(payload["Address"]))
        return

    for m in payload.get("Messages") or []:           # array, always
        number = to_e164(m["Msisdn"])                  # add the missing '+'
        record(m["MessageId"], m.get("Status"), number, m.get("OccurredAtTime"))

        if m.get("ContainsActionWord"):
            suppress(number)                           # STOP inside a normal reply

        if event_name == "sms-message-failed":
            detail = ex.get(f"/v2/messages/{m['MessageId']}")
            reason = (detail or {}).get("data", {}).get("reason")
            record_failure(m["MessageId"], reason)
```

Build the handler to cope with retries, duplicates and out-of-order arrival:

- Return 200 immediately and process asynchronously, so a slow handler does not
  trigger retries that turn one event into many.
- Be idempotent. Key on `MessageId` + `Status`; assume any callback can arrive
  twice, and that a batch can partly overlap a previous batch.
- Do not assume ordering. A delivered event can arrive before the local send
  record has committed. Upsert rather than update.
- Log the raw body while integrating. Several enums (`Status`,
  `ConversationStatus`, `SenderType`, `MessageCoding`) are best learned by
  observation.
- Handle the opt-out signal twice over: the dedicated `sms-inbound-opted-out`
  event and `ContainsActionWord` on an ordinary inbound message. Missing the
  second means keeping someone on a list who asked to leave.

The endpoint must be a publicly reachable HTTPS URL you host. Esendex cannot
reach `localhost`, so local development needs a tunnel.

## Authentication

`PUT /v2/webhooks/authentication-methods`. A maximum of one method per account;
specifying more than one fails with 400. Changing the method applies
automatically to all existing subscriptions on the account, which also means
changing it is an account-wide event that can break other consumers. Success is
201; confirm the change by watching callbacks arrive authenticated.

The body has three slots; fill exactly one and leave the others null:

```python
ex.put("/v2/webhooks/authentication-methods", {
    "oauth": None,
    "apiKey": {"key": "X-Webhook-Token", "value": "<shared secret>", "asQueryParam": "True"},
    "basic": None,
})
```

| Method | Concept |
| --- | --- |
| Custom headers / API key | A shared secret your endpoint checks on each request |
| Basic | Username and password, or a pre-encoded token |
| OAuth2 / bearer token | Esendex fetches a token from your authorization server and sends `authorization: Bearer {token}`. A token is requested when sending data, and also when a webhook is created or modified |

### Method fields

OAuth: send the snake_case fields `client_id`, `client_secret` and `token_url`,
and log the response.

Basic auth: send `username` and `password`, or a pre-encoded value in `token`. Use
`token` if a pre-encoded value is available, username and password otherwise.

API key: `asQueryParam` is described as "Default = 'false'. Needs to be set to
'True' to use this authentication method", which means the key is delivered as a
query parameter. This skill does not cover header delivery, so test it before
relying on it. A secret in a query string also ends up in access logs at both
ends, so tell the user before they choose this method.

Prefer API key or basic unless the user specifically needs OAuth; they have fewer
fields to get right on the first attempt.

### Linking authentication to subscriptions

Authentication is applied account-wide, and the create-subscription call returns no
body, so there is no authentication-method id to capture. Each subscription
carries a `requiresAuthentication` flag.

If callbacks for a subscription arrive without authentication, check that flag
first. Raise it with the user; do not debug their authorization server, and
suggest their account manager confirm how auth is wired to subscriptions on their
account.

There is no GET or DELETE for authentication methods, so the configured method can
neither be read back nor removed, only overwritten with another PUT.

### Scope of this authentication

This is transport authentication: Esendex proving itself to the receiving
endpoint. There is no HMAC signature over the payload, no timestamp, and no
nonce, so verification relies on the configured authentication method and the
endpoint has no separate way to check the integrity of the body. Points to pass
on to the user:

- Treat an unauthenticated request as untrusted and drop it.
- For anything consequential, re-read state from the API
  (`GET /v2/messages/{MessageId}`) before acting - for example before refunding
  something or marking an account closed.
- Rotate the secret by overwriting the authentication method. There is no
  overlap window and in-flight callbacks may fail during the switch, so schedule
  the change.

Payloads contain message bodies, recipient numbers and opt-out signals, so the
endpoint processes personal data on every request. HTTPS only, authenticate it,
keep it off any host that is not in scope for your data-protection posture, and
do not retain full message bodies in application logs indefinitely: log the
`MessageId` and drop the `Body`.
