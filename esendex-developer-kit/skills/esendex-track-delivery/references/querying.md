# Querying messages, requests and click metrics: full detail

Companion to `SKILL.md`.

Everything here is v2 REST, JSON, camelCase, `X-Api-Key` + `AccountReference`
headers. Failure reasons are strings in a `reason` field. There are no numeric
failure codes in v2.

## Response envelope

Every list endpoint wraps results the same way:

```json
{ "data": { "messages": [ ... ], "totalCount": 13191, "currentPage": 1, "totalPages": 1320 } }
```

The array key varies by endpoint: `messages`, `requests`, `requestsData`,
`visitsData`. `ex.paginate(path, params, key="messages")` walks `totalPages` for
the caller; omitting `key` takes the first list-valued key inside `data`, which
is sufficient for single-array responses.

`pageSize` accepts 1-1000 and defaults to 1 on every list endpoint. A bare
`ex.get("/v2/messages")` returns exactly one message and looks identical to an
account that has only ever sent one message. Always go through `paginate()`, which
sets 1000, or set the page size explicitly.

## Endpoint by endpoint

### GET /v2/messages - all outbound and inbound

The general-purpose query. Filters:

| Property | Type | Notes |
| --- | --- | --- |
| accountReference | Array | List of account references |
| requestId | GUID | Filter to one send request |
| conversationId | GUID | Unique per account+recipient; returns the whole thread both directions |
| status | String | `Delivered \| Received \| Failed \| In Progress` |
| reason | String | See the reason tables below |
| msisdn | String | International format, e.g. `447xxxxxxxxx`. Matches messages to *and* from the number |
| destinationCode | String | Nullable. 2-letter ISO 3166 |
| originator | String | `from` for outbound, `to` for inbound - VMN, shortcode or senderId |
| requestName | String | Nullable, optional name given at send time |
| channel | String | `SMS` (the messages-from-request page also lists `RCS`, `Email`) |
| messageType | String | `Unknown \| MarketingAndResearch \| NotificationsAndReminders \| AuthenticationAndSecurity \| PaymentsAndCollections \| InternalOperations \| CustomerSupport \| Conversational` |
| source | String | Which product area produced the message |
| startTime / endTime | dateTime | Compared against `submittedAt`, inclusive both ends |
| pageSize / pageNo | Integer | 1-1000 / 1+. Both default 1 |
| sortOrder | String | `Asc \| Desc`. Default `Desc` |
| sortBy | String | `Status \| submittedAt \| lastupdatedTimestamp \| channel \| messageType \| source \| requestName`. Default `submittedAt` |
| retrieveMessageBody | Boolean | Default TRUE. Set false for large status-only sweeps |
| direction | String | `Outbound \| Inbound` |

`MessageId`, `Route`, `SubmittedBy` and `RcsType` may also be accepted as
filters. Test them before relying on them, and do not promise them to a user.

Parameter names appear in both camelCase (`pageSize`) and PascalCase
(`PageSize`). The bundled client sends both spellings of the paging parameters
for this reason. If a filter appears to be ignored, try the other casing before
concluding the filter does not work.

Example response row:

```json
{
  "messageId": "8eb5fe15-...", "requestId": "c5a5eddc-...",
  "accountReference": "EXUK0000000", "requestName": "jwP9QjVqD1",
  "source": "TEST-FRAMEWORK", "channel": "SMS",
  "messageType": "MarketingAndResearch", "originator": "71460491",
  "isBillable": true, "msisdn": "+447700900124",
  "status": "Sent", "reason": "Delivered",
  "destinationCode": "GB", "messagePartCount": 1, "networkUsed": "Sandbox",
  "submittedAt": "...", "sentAt": "...", "lastUpdateTimestamp": "...",
  "direction": "Outbound"
}
```

`status` and `reason` vary independently, as this row shows: `status: "Sent"`
with `reason: "Delivered"`. `Sent` is not in the filterable `status` enum.

### GET /v2/messages/{messageId} - one message, more fields

No query filters. Returns everything the list view returns plus:

| Field | Purpose |
| --- | --- |
| `content` | The body text actually sent |
| `characterCount` | Real length after variable substitution |
| `characterSet` | `Gsm` / unicode - explains part-count surprises |
| `variables` | The merge values used, as a JSON string, e.g. `"{}"` |
| `dynamicFieldsUsed` | Whether personalisation was in play |
| `requestedChannel` | The channel asked for at send time |

This is the call for "what exactly was sent to this person, and did the
personalisation resolve?" A handler for the failed webhook event also needs it,
because the webhook payload has no failure reason.

404 body: `{"errors":[{"errorCode":"message_not_found", ...}]}`.

### GET /v2/inbox - inbound only

Same filter set as `/v2/messages`, plus:

| Property | Type | Notes |
| --- | --- | --- |
| includeDelete | Boolean | Default FALSE. TRUE also returns soft-deleted messages, **with all PII removed** - they exist only for billing reconciliation |

`includeDelete` is not a recovery mechanism. A deleted inbound message returns
without its content, so the row is only useful for counting billable inbound
traffic. Tell the user this up front.

Inbound rows carry `status: "Received"`, `reason: "Inbound"`, `direction:
"Inbound"` and `messageType: "Inbound"` or `"Conversational"`. Some rows carry
`isRead` and some do not, so treat it as optional and use `.get("isRead")`.

`msisdn` values can arrive in more than one format, and `destinationCode` can be
lowercase (`"gb"`) as well as uppercase (`"GB"`). Normalise numbers with
`to_e164()` and case-fold destination codes before comparing anything.

### GET /v2/requests - campaign rollups

The parameter names differ from the message endpoints, in particular
`RequestReason` (not `reason`) and `RequestedOriginator` (not `originator`).
There is no `msisdn`, `conversationId`, `direction` or `retrieveMessageBody` here;
it is a request-level view.

| Property | Notes |
| --- | --- |
| AccountReference | Array |
| RequestId | GUID |
| Status | `Delivered \| Received \| Failed \| In Progress` |
| RequestReason | Reason enum, request-level variant (see below) |
| RequestedOriginator | The sender used |
| RequestName | Nullable |
| Channel, MessageType, Source | As per `/v2/messages` |
| StartTime / EndTime | Against `submittedAt` |
| PageSize / PageNo / SortOrder / SortBy | Default 1 / 1 / `Desc` / `submittedAt` |

Response rollup fields:

```json
{
  "requestId": "74b714b4-...", "accountReference": "EXUK0000000",
  "source": "InboundNetworkEventHandler", "requestedOriginator": "71460491",
  "destinationCodes": ["GB"], "dynamicFieldsUsed": false,
  "channel": "SMS", "messageType": "Inbound", "characterSet": "gsm",
  "status": "Success", "failureReason": "",
  "messageCount": 1, "messagePartCount": 1,
  "sentMessageCount": 1, "sentMessagePartCount": 1,
  "failedMessageCount": 0, "failedMessagePartCount": 0,
  "submittedAt": "...", "lastUpdateTimestamp": "..."
}
```

Three characteristics of that block require care:

1. `sentMessageCount` means *handed to the carrier*, not *delivered to a
   handset*. `messageCount - sentMessageCount - failedMessageCount` is not a
   delivered figure either. If a client asks "how many were delivered", count
   the messages whose `reason` is `Delivered` (or
   `PartiallyDelivered`, stated as such) from `/v2/requests/{id}/messages`.
2. `status: "Success"` and `failureReason` appear here, but the `Status`
   filter accepts `Delivered | Received | Failed | In Progress` and the reason
   filter is called `RequestReason`. The request-level response vocabulary and
   the request-level filter vocabulary differ, so pull unfiltered and classify
   locally.
3. `failedMessageCount` is a point-in-time number that keeps rising. Anything
   awaiting a delivery receipt is in neither bucket yet, and `MessageExpired`
   only lands once the validity window elapses.

The `messagePartCount` / `sentMessagePartCount` pair is the billing view; the
`messageCount` pair is the recipient view. A 2-part message to 100 people is
`messageCount: 100, messagePartCount: 200`. Do not quote part counts as
recipients.

### GET /v2/requests/{requestId} - one request

Takes no query parameters. It may return a `messages` array like
`/v2/requests/{requestId}/messages` instead of the rollup object returned by
`/v2/requests`, so inspect what comes back before writing code against it. For a
single request's rollup counts, use `/v2/requests?RequestId={id}`.

### GET /v2/requests/{requestId}/messages - per-message within one campaign

Same filter table as `/v2/messages` including `retrieveMessageBody`,
`direction` and `includeDelete`. This is the primary endpoint for failure triage:
scope to one campaign, pull every message, group by `reason` locally.

400 `invalid_request_id` if the path GUID is missing or malformed.

### GET /v2/url-shortener/visits and /v2/url-shortener/visits/{requestId}

Click metrics come back in one of two body shapes: `requestsData`
(per-request aggregates) or `visitsData` (per-click detail), and each of these
two paths serves one of them. Call the collection path first, look at whether the
response carries `requestsData` or `visitsData`, and branch on that, not on the
path you believe you called.

Aggregate row: `requestId`, `requestName`, `requestSubmittedAt`,
`totalShortUrlsCreated`, `totalShortUrlsVisited`, `totalVisits`.

Per-click row: `requestId`, `requestName`, `requestSubmittedAt`, `shortUrl`,
`longUrl`, `channel`, `addressValue` (the recipient's number),
`accessTimestamp`, `ipAddress`, `userAgent`, `os`.

Filters on the collection endpoint are only `pageSize`, `pageNo`, `sortOrder`,
`sortBy` (`RequestSubmittedAt | RequestName`), `startTime`, `endTime`.

`totalVisits` counts clicks, not people, so a click rate quoted as a percentage
of recipients needs `totalShortUrlsVisited`, not `totalVisits`.

Only requests sent with `[shorten:...]` produce any data here, and shortening is
unavailable on trial accounts, so an empty result may mean "not enabled" rather
than "nobody clicked". Check with the sender before reporting zero engagement.

Privacy: per-click rows tie an IP address, user agent and OS to an identifiable
phone number. That is personal data about an individual's browsing. Use it for
aggregate campaign reporting. Do not build per-person profiles from it, and do
not export it into a spreadsheet or BI tool with weaker access control than the
platform without the user understanding exactly what the file contains.

## Reason values by endpoint

Each endpoint has its own set of `reason` values. None is a superset of the
others, so no single list is complete.

| Reason | /v2/messages | /v2/inbox | /v2/requests (RequestReason) | /requests/{id}/messages |
| --- | --- | --- | --- | --- |
| Delivered | yes | yes | yes | yes |
| PartiallyDelivered | yes | - | yes | yes |
| Inbound | yes | - | yes | yes |
| MsisdnInvalid | yes | yes | yes | yes |
| senderIdInvalid | yes | yes | yes | yes |
| OptedOut | yes | yes | yes | yes |
| LandlineNotAllowed | yes | yes | yes | - |
| DestinationNotAllowed | yes | yes | yes | yes |
| DisallowedContent | - | - | yes | yes |
| MessagePartCountExceeded | yes | yes | yes | yes |
| SendingLimitExceeded | yes | yes | yes | yes |
| WithinQuietHours | yes | yes | yes | yes |
| OutsideBusinessHours | yes | yes | yes | yes |
| MessageExpired | - | yes | - | - |
| NetworkFailed | yes | yes | - | - |
| InternalError | - | - | yes | - |
| EdgeFailed | - | - | - | yes |
| EdgeSubmitted | - | - | - | yes |
| FailedToRoute | - | - | - | yes |
| Unprocessable | - | - | - | yes |

A value that can be filtered on at one endpoint may return 400 or an empty result
at another. When a complete picture is required, pull
unfiltered for the time window or `requestId` and group by `reason` in Python.
That also protects against response-only values such as `Sent` and `Success`
that appear in no filter enum.

`senderIdInvalid` is lowercase-first while every sibling value is PascalCase. Compare case-insensitively.

## Retry classification

| Reason | Class | Action |
| --- | --- | --- |
| Delivered | Success | Nothing |
| PartiallyDelivered | Partial success | Some parts of a concatenated message arrived. Report it as partial, not delivered |
| Inbound | Not a failure | Marks direction |
| EdgeSubmitted | In flight | Handed onward, no receipt yet. Re-poll later |
| OptedOut | Permanent - never retry | The recipient withdrew consent. Retrying is a compliance breach, not a technical error. Mirror into suppressions (`esendex-manage-contacts`) |
| MsisdnInvalid | Permanent | Bad number. Fix or drop it at source |
| senderIdInvalid | Permanent, but a sender-configuration fault | The sender wasn't accepted. Fix the originator and the same recipients can be resent |
| LandlineNotAllowed | Permanent | Not a mobile |
| DestinationNotAllowed | Permanent | Country not enabled on the account |
| DisallowedContent | Permanent | Content blocked. Rewriting and resending is a content decision, not a retry |
| MessagePartCountExceeded | Permanent | Shorten the message, then resend |
| MessageExpired | Permanent for that send | Validity elapsed. Resendable, but check why delivery was delayed first |
| SendingLimitExceeded | Deferred | Retry after limits reset (`esendex-setup-account`) |
| WithinQuietHours | Deferred | Retry outside the window |
| OutsideBusinessHours | Deferred | Retry inside the window |
| NetworkFailed | Transient | Retry is reasonable |
| EdgeFailed | Transient | Retry is reasonable |
| FailedToRoute | Transient | Retry is reasonable; raise a cluster with Esendex support |
| InternalError | Transient | Retry; raise a cluster with Esendex support |
| Unprocessable | Transient/unclear | The value alone does not say why. Inspect a sample with `GET /v2/messages/{id}` before deciding |

Check for `senderIdInvalid` early in an incident. It fails everything sent with
that originator, so it presents as "nobody received it". The cause is the sender
configuration, unrelated to the recipients, and the whole affected set is
resendable once the sender is fixed. Rule it out before investigating recipient
data or carrier problems.

## Timestamps and windows

| Field | Meaning |
| --- | --- |
| `submittedAt` | The platform accepted it. All `startTime`/`endTime` filters compare against this |
| `sentAt` | Handed to the network. Absent means still queued, not lost in transit |
| `lastUpdateTimestamp` | Most recent status change, i.e. when the receipt landed |

All UTC ISO 8601. Delivery latency is `sentAt` to `lastUpdateTimestamp` on a
delivered message. A message with `submittedAt` but no `sentAt` is queued on the
platform, which is a throughput or scheduling question, not a network one.

Because the filters are UTC and inclusive at both ends, a local "day" is not a
UTC day for most of the year in the UK. During BST, yesterday runs
`23:00Z` the day before to `23:00Z`. Building the window from
`date.today()` at midnight UTC drops the last hour of the client's evening, which
is the hour a late-evening campaign lands in, and includes an hour of the morning
they do not mean. Compute the boundaries from the
account's local timezone and convert, and state the window used in any number
reported.

## Worked queries

```python
from esendex_client import Esendex, to_e164

ex = Esendex()

# Everything about one recipient, both directions, as a thread.
msgs = list(ex.paginate("/v2/messages",
                        {"Msisdn": to_e164("07700900123")}, key="messages"))
convo = msgs[0]["conversationId"] if msgs else None
thread = list(ex.paginate("/v2/messages",
                          {"ConversationId": convo}, key="messages"))

# Status-only sweep over a large window, no bodies hauled back.
statuses = list(ex.paginate("/v2/messages",
                            {"StartTime": "2026-07-01T23:00:00Z",
                             "EndTime": "2026-07-02T23:00:00Z",
                             "RetrieveMessageBody": "false"}, key="messages"))

# One campaign, classified locally instead of by filter.
from collections import Counter
per_msg = list(ex.paginate(f"/v2/requests/{rid}/messages", key="messages"))
print(Counter(m.get("reason") for m in per_msg))
print(Counter(m.get("status") for m in per_msg))
```
