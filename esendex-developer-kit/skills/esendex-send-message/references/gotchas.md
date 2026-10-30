# Reference: gotchas in detail

Every row in the Gotchas table in `SKILL.md`, stated in full with what to do. The
API reference is at https://developer.esendex.co.uk.

## The retired v1 XML API

Two generations of the Esendex API exist. This skill covers v2 only.

**v1 (retired).** `POST /v1.0/messagedispatcher`, an XML `<messages>` document, a
`<sendat>` element inside the message for scheduling, HTTP Basic auth.

**v2 (current).** JSON over REST against `https://api.esendex.co.uk`, an `X-Api-Key`
header, and a separate schedule resource carrying `sendTime`.

If a request being written looks like XML, targets `/v1.0/messagedispatcher`, or uses
Basic auth, stop and rewrite it as v2 JSON; a v1-shaped request does not work with the v2
endpoints and API key. For scheduling, the difference is `<sendat>` inside the message
(v1) versus a schedule resource with `sendTime` (v2).

## Contacts per request

`addressBook.contacts` takes at most 10,000 contact ids in a single request.
`recipients[]` takes 1–50,000 objects.

Keep contact-id batches at or below 10,000 and page through anything larger.
Verify `addressBook.groups` with one small live send before relying on it.

## Square-bracket variables

Placeholders are square-bracketed names such as `[firstName]`, matched to keys in each
recipient's `variables` object. The `[shorten:https://...]` marker in the same field uses
the same bracket syntax.

Use `[name]` in `body.text` or a template's `content`, with a matching key in each
recipient's `variables`. Confirm with one live test before a large personalised run.
Check what a placeholder with no matching value renders as in that test; do not assume it
renders as empty. Note also that the GSM extended set includes `[` and `]`, each costing
two characters.

## `text` and `templateId` are mutually exclusive

`body` carries exactly one of `text` or `templateId`.

Supplying both is a 400. Supplying neither `recipients` nor `addressBook` is also a
400, as is omitting `from` when no default sender is configured on the account.

## Alphanumeric senders cannot receive replies

An alphanumeric sender such as `MyBrand` cannot receive replies, which matters for
opt-out compliance. It may also need pre-registration depending on the destination country's regulations, and a numeric
sender must be a VMN or short code the account actually owns.

A message ending "reply STOP to opt out" sent from an alphanumeric sender is
unfulfillable: the reply goes nowhere, and the promised opt-out route does not exist. With
an alphanumeric sender the opt-out route has to be a link or a phone number, or the sender
has to become a VMN or short code so replies can land. If a send pairs an alphanumeric
sender with STOP-style copy, flag it, do not send it. An arbitrary numeric sender
fails with `senderIdInvalid`, which is the first thing to check on any rejected send: the
sender, not the recipient.

## One emoji flips the message to Unicode

GSM fits 160 characters in a single part and 153 per part concatenated; Unicode (UCS-2)
fits 70 and 67. That is what `sms_part_count` implements.

`characterSet` defaults to `Auto`, which uses GSM unless the text contains a
character GSM cannot represent. One emoji or one non-Latin character therefore drops
capacity from 160 to 70 for the whole message: a plain 100-character message costs one
part, and the same message plus a single 🚚 costs two, doubling the cost for every
recipient. Cost the send with `sms_part_count` before submitting, and name the character
that raised the part count, since it is usually removable. The estimate is not a billing
guarantee - the billed figure is `messagePartCount` on the message record.

## `[shorten:...]` is unavailable on trial accounts

Write the marker with no space after the colon:
`[shorten:https://example.com/orders/12345]`.

The platform replaces the marker with a `uk.endx.io/abcd123` link unique per
recipient, which saves characters and makes per-recipient click tracking possible. It is
not available on trial accounts. If a send carrying a shortener marker fails on what looks
like a new account, the fix is upgrading the account, not retrying.

## Scheduling is UTC-only

The platform operates in UTC exclusively and exposes no timezone field. Datetimes are
ISO 8601 with `Z`: `2026-08-03T08:00:00.000Z` for `sendTime`, `YYYY-MM-DD` for throttle
dates, `HH:MM:SS` for time slots.

Establish the timezone the user means, convert to UTC, and state the conversion
applied so it can be checked: "9am on 3 August in London is 08:00Z." Passing
`09:00:00.000Z` for a British Summer Time 9am sends an hour early to everyone, and there is
no undo.

## Omitting `repeatTimes` repeats indefinitely

Omit `repeatTimes` with `frequency` set and the schedule repeats indefinitely. On a
marketing message that is a compliance and cost risk, and the body cannot be edited
afterwards. Always set an explicit count unless the user has clearly asked for indefinite recurrence,
and state the count set. `repeatTimes` without `frequency` errors; for a one-off, omit
both. Repeat occurrences link back to the original via `parentId`.

## `Weekdays` and `Weekends` as frequency values

`frequency` takes six values: `Daily`, `Weekly`, `Monthly`, `Annually`, `Weekdays`,
`Weekends`.

Send `Weekdays` or `Weekends` alone, never combined, and test with a short-lived
schedule if the user depends on it.

## The five-minute edit cutoff

An edit made inside the cutoff fails or does not take effect.

`PATCH /v2/schedules/delayed/{scheduleId}` changes only
`scheduleInformation.sendTime` and `dispatch.name` - not the text, recipients, sender or
frequency - and updates must land at least 5 minutes before the scheduled send time. If a
user asks to stop or change something going out in the next few minutes, say immediately
that the API window has probably closed and that they should use the portal or contact
support instead of retrying. Cancelling needs the `scheduleId`
specifically; a `requestId` or `messageId` will fail, as they identify different things.

## A 201 does not mean the schedule is valid

The delayed create endpoint returns 201 with a `scheduleId` and, in the same payload, a
`data.validationResult` that may report the schedule invalid.

Check `data.validationResult.isValid` on every delayed create, and read
`errors[]` (`propertyName`, `errorMessage`, `attemptedValue`, `severity`, `errorCode`)
when it is false. Without the check, success could be reported for a schedule that will
not fire. A throttle create carries no `validationResult`; verify it by reading back
`numberOfRecipients` and the echoed rate.

## Template read shape is not the write shape

The request sends `templateType: "Text"` and the response returns `type: "Text"`. The
request sends `channelSettings: {"sms": {"characterSet": "Auto"}}` and the response
returns `channelSettings: [{"channel": "Sms", "settings": "{\"CharacterSet\":\"Auto\"}"}]`
- an array whose `settings` is a JSON-encoded string with a PascalCase inner key. The two
shapes are not interchangeable.

Rebuild the write shape by hand; do not feed a GET response into a `PUT`. Send the
complete object on update, all five fields: `PUT` semantics make a partial body risky.
Note also that `GET /v2/templates` defaults to `PageSize=1`, so paginate or one template
will be read and the account concluded empty.

## Template tags

The body of `PATCH /v2/templates/{templateId}/tags` is `{"tagIds": ["<guid>"]}`.

Send `{"tagIds": [...]}` with tag GUIDs, never names. Success is 204 with no body.
It takes a full array, so assume it replaces the set, and verify on a throwaway template.

## Tags are managed in the portal

Templates carry `tags[]` and the tags endpoint accepts `tagIds`, but this skill covers no
endpoint to create, list, rename or delete a tag.

Treat tags as portal-managed. A user who wants templates tagged programmatically
must supply the GUIDs from the portal first; do not offer to create or enumerate them.

## Field names

Field names are case-sensitive.

| Field | Where |
| --- | --- |
| `timeSlotStart` | Throttle `throttleScheduleInformation` |
| `rateOfSend` | Throttle `throttleScheduleInformation` |
| `daysOfWeek` | Throttle `throttleScheduleInformation` |
| `contacts[].contactId` | Throttle create and add-recipients |
| `recipients[]` with `msisdn`, `variables`, `metaData` | Every send and schedule body, including add-recipients |
| Top-level `contacts[]` / `groups[]` | Delayed create (not an `addressBook` object) |
| `/v2/throttle-schedule/{id}/recipients` | Add-recipients path |

Use the names above. If a field appears to have no effect, check its spelling and casing
first.

## The API key header

The header is `X-Api-Key`. Sending the key under any other header name produces a 401.

Send `X-Api-Key`. The bundled client sets this header in one place.
