# Gotchas - detail behind the summary table

Companion to `SKILL.md`. One section per row of its Gotchas table, plus the version
guard. Each says what goes wrong, why it matters, and what to do.

## Numeric failure codes do not exist in v2

The earlier XML-based Esendex API (v1) returned numeric delivery failure
codes (0, 4, 6, 7, 8, 12, 13, 16, 17, 101, 102, 199, 200, 999) inside a
`<FailureReason>` element, authenticated with HTTP Basic, over paths such as
`/v1.0/messagedispatcher` and `/v1.1/messagebatches`.

v2 has no equivalent numeric code table. Every v2 outcome is a string in a JSON
`reason` field - `Delivered`, `MsisdnInvalid`, `senderIdInvalid`, `OptedOut`,
`MessageExpired` and the rest of the set tabulated in `SKILL.md`. HTTP status codes
(400, 401, 404, 429) describe the HTTP request, and say nothing about message outcome.
A numeric failure-code table presented as v2 is incorrect.

If you find yourself writing a numeric failure-code table or parsing a
`<FailureReason>` element, stop and check the relevant page in the Esendex developer
docs at https://developer.esendex.co.uk. v1 examples look plausible and are easy to
recall, so a re-read of your own code will not catch them; checking the docs will.
`esendex-setup-account` lists the rest of the retired v1 surface.

## pageSize defaults to 1

Every list endpoint takes a `pageSize` of 1-1000 and defaults it to 1.

A bare `GET /v2/messages` returns a well-formed 200 with a `messages` array of
length one, which looks the same as an account that has sent exactly one message.
It is easy to conclude from this that the account is empty or the filter is wrong,
and to tell a client their campaign did not send.

Never rely on the default. Set the page size explicitly, or go through
`ex.paginate()`, which sets 1000, sends every parameter-name variant
(`PageSize`/`pageSize`, `PageNo`/`PageNumber`) and walks `totalPages`. Treat a result
count of exactly 1 as a paging problem until confirmed otherwise.

## sentMessageCount means handed to the carrier

`GET /v2/requests` returns `messageCount`, `sentMessageCount`, `failedMessageCount`,
`messagePartCount` and `sentMessagePartCount`. The names invite reading
`sentMessageCount` as a delivered figure, but it means accepted by the carrier;
delivery is only knowable from a per-message `reason`. Subtraction does not give a
delivered figure either: `messageCount - sentMessageCount - failedMessageCount` is not
a delivered figure, because anything awaiting a receipt sits in no bucket yet.

The two count families are also distinct and easily conflated. `messageCount` and
`sentMessageCount` are recipients; `messagePartCount` and `sentMessagePartCount` are
billable parts. A 2-part message to 100 people is `messageCount: 100,
messagePartCount: 200`. Never quote part counts as recipients.

For a delivered figure, pull `/v2/requests/{requestId}/messages` and count
rows whose `reason` is `Delivered`, plus `PartiallyDelivered` reported separately as
partial. Quoting `sentMessageCount` as delivery overstates success and understates
failures, and delivery numbers get repeated to clients in writing.

## MessageExpired arrives late, so failure counts keep climbing

`MessageExpired` only appears once the validity window has elapsed, which can be hours
after the send. Until then those messages are in an in-progress state and appear in
neither the delivered nor the failed bucket. `failedMessageCount` is therefore a
point-in-time number that keeps rising, not the campaign's final failure total;
`references/querying.md` records the same behaviour against the `/v2/requests` rollup
fields.

A related check belongs here. If `status` is largely `In Progress`, or rows have
`submittedAt` but no `sentAt`, nothing has failed: the send is still queued on the
platform, which is a throughput or scheduling question, not a delivery failure. Do
not report failure for messages that have not failed.

Re-run the query immediately before quoting a client a number, and give the figure
as at a timestamp with a note that it may rise. For example: of 4,000 recipients in
the window 23:00Z 21 Jul to 23:00Z 22 Jul, 3,412
delivered, 88 partially delivered, 401 failed (380 of them `senderIdInvalid`,
recoverable and being resent), 99 still in progress, as at 14:20 UTC, and the failed
figure may rise as validity windows expire.

## A senderIdInvalid cluster looks like total non-delivery

When a client reports that nobody received their messages, the cause could be
recipient data, carrier problems or the sending account's own configuration. A
sender-configuration fault is the one most likely to affect every message at once,
and it is quick to fix.

`senderIdInvalid` fails every message sent with that originator, so it presents
as total non-delivery. The cause is the sender configuration, unrelated to the
recipients or their networks, and the entire affected set is resendable once the
sender is corrected. Check for it first, before examining the recipient data.

Other dominant clusters, in the order they are worth checking:
`MsisdnInvalid` across the board points at a bad import or a formatting problem in the
source list. `DestinationNotAllowed` means the country is not enabled
on the account. `SendingLimitExceeded` or `WithinQuietHours` means policy deferred or
dropped the messages; nothing failed technically, and the fix is scheduling.

Scope the incident to a `requestId`, pull every message for it unfiltered, group by
`reason`, and look for a single dominant value before looking at network causes. "All
4,000 failed with one reason" and "40 failed with six different reasons" are different
incidents, and a bare "37% failed" needs the retry classification before anyone can
act on it. Fix the originator via `esendex-setup-account`, then
resend via `esendex-send-message`. Note that `senderIdInvalid` is lowercase-first while
every sibling reason value is PascalCase, so compare case-insensitively.

## "Yesterday" is not a UTC day during BST

`startTime` and `endTime` are UTC and compare against `submittedAt`, inclusive at both
ends. A UK account during British Summer Time is one hour ahead of UTC, so its
yesterday runs 23:00Z the day before to 23:00Z. Midnight UTC to midnight UTC is only
correct in UK winter, or for any account whose local timezone matches UTC.

Building the window from `date.today()` at midnight UTC drops the last hour of the
client's evening - the hour a late-evening campaign lands in - and includes an hour of
the following morning that the client does not mean. Nothing in the response shows
this; the report just covers the wrong period.

Compute the boundaries in the account's local timezone, convert to UTC,
and state the window used in any number reported.

## includeDelete strips PII

`GET /v2/inbox` accepts `includeDelete`, default FALSE, where TRUE also returns
soft-deleted messages "with all PII removed". It is not a recovery mechanism: the
personally identifying content, including the message body, is removed before the row
is returned, so the rows exist only for billing reconciliation.

Use it to count billable inbound traffic and nothing else. When a user asks to
recover the text of a deleted message, tell them straight away that this API cannot
return it.

## URL-shortener metrics come in two shapes

Click metrics come back in one of two body shapes: `requestsData`, per-request
aggregates, or `visitsData`, per-click detail. The paths `/v2/url-shortener/visits`
and `/v2/url-shortener/visits/{requestId}` each serve one of them.

Call the collection path `/v2/url-shortener/visits`, inspect whether the
response carries `requestsData` or `visitsData`, and branch on that, not on the path
you believe you called.

## Reading one event's subscriptions

The subscriptions for a single event can be read with
`GET /v2/webhooks/events/{eventType}` or with
`GET /v2/webhooks/subscriptions?eventType={eventType}`.

Try both forms and use whichever returns data. `references/webhooks.md`
carries a short loop that does exactly that. Judge the result by the body, and do not
assert a particular success code.

## Only one webhook authentication method per account

`PUT /v2/webhooks/authentication-methods` takes a body with three slots - `oauth`,
`apiKey`, `basic` - and a maximum of one method is permitted per account. Specifying
more than one fails with 400. Changing the method applies automatically to every
existing subscription on the account. Success is 201 Created; confirm the change by
watching callbacks arrive authenticated.

Fill exactly one slot and leave the other two null. Treat a change as an
account-wide event that can break other consumers, and schedule secret rotation, since
there is no overlap window and in-flight callbacks will fail during the switch.

## OAuth field names

The OAuth method takes snake_case fields: `client_id`, `client_secret` and
`token_url`. Esendex fetches a token from the user's authorization server with them
and sends it as `authorization: Bearer {token}`.

Prefer API key or basic authentication unless OAuth is specifically required; they
have fewer fields to get right. If OAuth is needed, send the snake_case form, log the
response, and confirm callbacks arrive authenticated before reporting it configured.

Related: on the API key method, `asQueryParam` is described as "Default = 'false'.
Needs to be set to 'True' to use this authentication method", which means the key is
delivered as a query parameter. A secret in a query string lands in access logs at
both ends, so tell the user before they choose this method.

## Basic auth: token or username and password

The basic method takes `username` and `password`, or a pre-encoded value in `token`.
A success response alone does not confirm that the fields were recognised, so a
misnamed field can go unnoticed.

Send `token` if a pre-encoded value is available, username and password
otherwise, and verify by observing whether callbacks arrive authenticated. Do not
report the method as configured on the strength of the response code alone.

## No HMAC signature on webhook payloads

The authentication methods above are transport authentication: Esendex proving itself
to the receiving endpoint. Webhook payloads carry no HMAC signature, no timestamp and
no nonce, so verification relies on the configured authentication method, and the
endpoint has no separate way to check the integrity of the body.

Treat an unauthenticated request as untrusted and drop it. For anything
consequential, re-read state with `GET /v2/messages/{MessageId}` before acting - for
example before issuing a refund or closing an account. Explain this to the user,
because it determines what the handler should decide on its own.

## Linking the authentication method to subscriptions

Authentication is account-wide, with one method per account. The create-subscription
call returns 201 with no body, so there is no authentication-method id to capture from
it. Subscriptions carry a `requiresAuthentication` flag.

Set `requiresAuthentication` when creating the subscription and log the result. If
callbacks for a subscription arrive without authentication, check this flag first.
Raise it with the user; do not debug their authorization server.
Suggest their account manager confirm how authentication is wired to subscriptions on
their account. Note also that the configured method can neither be read back nor
removed, only overwritten with another PUT.
