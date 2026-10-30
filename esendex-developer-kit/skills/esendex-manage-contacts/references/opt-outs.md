# Opt-out endpoints in full

Three endpoints on one resource. This list is the authoritative answer to "am I
allowed to message this number?"

## Contents

- [Shared shapes](#shared-shapes)
- [The field that has three names](#the-field-that-has-three-names)
- [POST /v2/optouts](#post-v2optouts)
- [GET /v2/optouts](#get-v2optouts)
- [DELETE /v2/optouts](#delete-v2optouts)
- [Defensive checks](#defensive-checks)

## Shared shapes

`X-Api-Key` on all three. `Content-Type: application/json` on the POST.
`AccountReference` as a header on the GET and the DELETE, and as a body field
`accountReference` on the POST. See `esendex-setup-account`,
`references/conventions.md`.

The opt-out record, as returned by both the POST and the GET:

| Field | Type | Notes |
| --- | --- | --- |
| `id` | GUID | The record's own id. No endpoint accepts it - you cannot get, update or delete an opt-out by id |
| `accountReference` | string | |
| `channel` | string | `SMS` |
| `value` | string | The suppressed address, E.164 with the leading `+` |
| `createTimestamp` | ISO 8601 UTC | GET only. Absent from the POST 201 body |

Removal is by `Channel` + `Value`, not by `id`, and there is no read-one
endpoint.

Error bodies use shape A (`{"errors": [{"errorCode", "errorMessage"}]}`) for 400
on all three and for 401 on the POST; the GET and DELETE return 401 in shape B
(the `internalErrors` envelope). Parse both shapes, and parse defensively: do not
let an unexpected error body crash the handler.

There are no opt-out-specific error codes to branch on, unlike groups, which name
`group_not_found` and similar codes. Read `errorMessage`.

## The field that has three names

The same phone number has a different name on each of the three calls. Unknown
parameters are ignored, not rejected, so a call that uses the wrong name returns
success without doing anything.

| Call | Where | Name | Case |
| --- | --- | --- | --- |
| POST | request body | `value` | lower case |
| GET | query string | `Address` | initial capital |
| DELETE | query string | `Value` | initial capital |
| POST / GET | response body | `value` | lower case |

A filtered read therefore sends `Address` and reads back `value`. There is no
`Address` field in any response, and no `Value` query parameter on the GET.

## POST /v2/optouts

Suppresses an address. This is the call to make when consent is withdrawn
out-of-band, whether by email, phone call, form or CRM flag, or when mirroring a
suppression from your own system.

**Path:** `https://api.esendex.co.uk/v2/optouts`. **Method:** POST.
**Headers:** `X-Api-Key`, `Content-Type: application/json`.

**Success:** `201 Created` for a new record. `200 OK` if the opt-out record
already exists.

**Request body**

| Parameter | Type | Required | Constraint |
| --- | --- | --- | --- |
| `accountReference` | string | Required | `EXUK0000000` form. Opt-outs are per account reference, not global across a customer's accounts |
| `channel` | string | Required | "The channel to be used for the message. Enum e.g. SMS". Use `SMS` |
| `value` | string | Required | "The customer value which is to be updated". E.164 with the leading `+`. Normalise before sending |

```json
{"accountReference": "EXUK0000000", "channel": "SMS",
 "value": "+447700900410"}
```

**Response (201)**

```json
{"data": {"id": "8ef8ae1a-8af9-4348-b527-746b22e6d361",
          "accountReference": "EXUK0000000", "channel": "SMS",
          "value": "+447700900410"}}
```

No `createTimestamp` on the create response, though the GET returns one.

On a 200 for an existing record, check that `data.id` exists before reading it
from the result of a defensive re-suppression.

Adding is idempotent, so there is no need to check whether a number is already
suppressed before suppressing it. The 201 or 200 shows which occurred, and
suppressing twice is not an error. When in doubt, suppress.

Normalise to E.164 with `to_e164()` before writing, so that `07700900410` and
`+447700900410` cannot become two records and the write side and the scrub side
agree.

**Errors**

| Code | Shape | Trigger |
| --- | --- | --- |
| 400 | A | Incorrect syntax, or an incorrect/missing required property. "You should not repeat the request without modifications" |
| 401 | A, `UnauthenticatedError` | Missing or incorrect auth. Note shape A and the capitalised code here, against shape B on the other two endpoints |

No 409: the duplicate case is the 200, not an error. Validate `value` with
`to_e164()` before sending: an ill-formed number may be accepted and stored,
producing a suppression record that never matches a real recipient.

## GET /v2/optouts

The list. There is no "is this number opted out?" endpoint, so this endpoint is
also how that question is answered: filtered for one address, or pulled whole and
turned into a set for a campaign scrub.

**Path:** `https://api.esendex.co.uk/v2/optouts`. **Method:** GET.
**Success:** `200 OK`. **Headers:** `X-Api-Key`, `AccountReference`.

**Query parameters**

| Parameter | Values / constraint |
| --- | --- |
| `AccountReference` | Duplicate of the required header |
| `Address` | "The number MSISDN the opt out is associated". Filters on the field returned as `value`. Send the full E.164 number |
| `Channel` | "provided as a string e.g. SMS" |
| `StartTime` | ISO 8601, `yyyy-MM-ddThh:mm:ssZ`. Filters on `createTimestamp`, the only timestamp the record has |
| `EndTime` | Same, upper bound |
| `SortBy` | Use `createdAt`; an opt-out record has no name field |
| `SortOrder` | `Asc` / `Desc`. Default descending |
| `OptOutMethod` | `Stop` or `Manual`. See below |
| `PageNo`, `PageSize` | `PageSize` defaults to 1 - a bare GET reads one record and makes a populated suppression list look nearly empty |

`OptOutMethod` is the parameter a consent audit needs:

| Value | Meaning |
| --- | --- |
| `Stop` | "has been received by a customer replying opt out" - the customer withdrew consent themselves, by replying with a keyword |
| `Manual` | "has been added directly into the Connect platform" - the opt-out was added on the account side |

This separates a customer-initiated withdrawal from an internal suppression. The
method can be filtered on but is not returned: `optOutMethod` is not on the
record, from either the POST or the GET. To obtain the
method per number, query once with `OptOutMethod=Stop` and once with `Manual` and
tag the two result sets yourself.

**Response**

```json
{"data": {"optOuts": [
  {"id": "b5a5a418-294a-42a1-ae23-ecb2168dcd39",
   "accountReference": "EXUK000", "channel": "SMS",
   "value": "+447700900123",
   "createTimestamp": "2024-07-05T13:59:50.064193Z"}],
  "totalCount": 1, "totalPages": 1, "currentPage": 1}}
```

Array key `optOuts`, with a capital O, which the paginator needs verbatim. An
empty list is a 200 with an empty `optOuts` array and `totalCount: 0`.

Handle the empty case carefully. An empty result from a scrub looks identical to
"nobody on this account has opted out", so code that treats a failed or truncated
read as empty will message everybody. If the scrub errors, returns 401 or
paginates partially, abort the send; do not treat it as an empty suppression set.

**Errors**

| Code | Shape | Trigger |
| --- | --- | --- |
| 400 | A | Incorrect syntax or an incorrect/missing required property - usually a missing or malformed `AccountReference` |
| 401 | B | Missing or incorrect auth |

No 404. A filter matching nothing is a 200 with an empty array.

## DELETE /v2/optouts

Removes a suppression, which re-enables messaging to someone who previously said
stop. The constraints on when to do this, and what to do
with a request to clear opt-outs in bulk, are in `SKILL.md`.

**Path:** `https://api.esendex.co.uk/v2/optouts?Channel=String&Value=String`.
**Method:** DELETE. **Headers:** `X-Api-Key`, `AccountReference`.

**Success:** `200 OK`. Treat the body as empty and do not parse it.

**Query parameters**

| Parameter | Type | Required | Constraint |
| --- | --- | --- | --- |
| `Value` | string | Required | "The MSISDN value which will remove the opt out for". Capital V - the POST body field is lower-case `value` |
| `Channel` | string | Required | "The channel which will opted out for. Possible values: SMS" |
| `AccountReference` | string | Optional | Also sent as the required header; sending both is harmless |

Both `Value` and `Channel` are required: this is a delete-by-composite-key, not
by id, and the record's own `id` is not accepted. There is no way to delete every
opt-out in one call.

**Errors**

| Code | Shape | Trigger |
| --- | --- | --- |
| 400 | A | Incorrect syntax or an incorrect/missing required property - a missing `Value` or `Channel` |
| 401 | B | Missing or incorrect auth |

Deleting an opt-out that does not exist returns the same 200 as deleting a real
one, so the call cannot confirm it removed anything. A `Value` in the wrong format
(no leading `+`, national form, a stray space) also returns 200 while the
suppression stays in place. The person stays suppressed, which is the safe
outcome, but the removal has not happened. Verify by
reading back with `GET /v2/optouts?Address=...&Channel=SMS` and confirming the
record is gone.

## Defensive checks

| Situation | What to do |
| --- | --- |
| `/v2/optouts` versus the contact-level `smsoptOutStatus` / per-address `optOutStatus` | Do not assume they are synchronised in either direction: adding an opt-out may not flip a contact's field, and writing the contact field may not create an opt-out record. Treat `/v2/optouts` as authoritative for "may I message this number?" and the contact fields as possibly-stale metadata. See `references/contacts.md` |
| The `channel` value | Use `SMS` |
| POSTing an opt-out that already exists | Expect a 200; check `data.id` exists before reading it |
| Writing `value` | Normalise to E.164 with `to_e164()` first |
| Reading the opt-out method per record | Query by `OptOutMethod=Stop` and `Manual` separately and tag the results |
| Filtering by `Address` | Send the full E.164 number |
| Deleting an opt-out | Read back with `GET /v2/optouts?Address=...&Channel=SMS` to confirm it has gone |
| Opt-outs across several account references | Add the opt-out to each account reference; records are per account |
| Bulk add or bulk remove | Does not exist. One address per call, on both the POST and the DELETE |
