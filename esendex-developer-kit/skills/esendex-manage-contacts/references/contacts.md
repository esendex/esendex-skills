# Contact endpoints in full

Seven endpoints, covering single contacts, search and bulk import.

## Contents

- [Shared shapes](#shared-shapes)
- [Body shape: single versus bulk](#body-shape-single-versus-bulk)
- [POST /v2/contacts](#post-v2contacts)
- [GET /v2/contacts/{contactId}](#get-v2contactscontactid)
- [GET /v2/contacts/filter](#get-v2contactsfilter)
- [PUT /v2/contacts/{contactId}](#put-v2contactscontactid)
- [DELETE /v2/contacts?contactId=](#delete-v2contactscontactid)
- [POST /v2/contacts/bulk](#post-v2contactsbulk)
- [PUT /v2/contacts/bulk](#put-v2contactsbulk)
- [Defensive checks](#defensive-checks)

## Shared shapes

Headers follow the account-wide pattern: `X-Api-Key` always, `Content-Type:
application/json` on anything with a body, `AccountReference` as a header on the
two list endpoints and as a body field (`accountReference`) on the writes. The
key header is `X-Api-Key`; see `esendex-setup-account`,
`references/conventions.md`.

Error bodies come in the shapes named in that same file: shape A is
`{"errors": [{"errorCode", "errorMessage"}]}`, shape B is the nested
`{"title", "status", "internalErrors": [{"metadata": {...}}]}` envelope. Contacts
endpoints use shape A for 400/404/409 and shape B for 401, with one exception:
`GET /v2/contacts/filter` returns its 401 in shape A with
`errorCode: "unauthenticatedError"`. Parse both.

The contact object, as returned on reads:

| Field | Type | Notes |
| --- | --- | --- |
| `contactId` | GUID | Named `id` in the bulk responses, `contactId` everywhere else |
| `accountReference` | string | |
| `firstName`, `lastName` | string | Max 500 characters each |
| `quickName` | string | Short name |
| `lastUpdatedBy` | string | Usually a GUID |
| `smsoptOutStatus` | string | `Subscribed` / `Unsubscribed`. Contact-level consent flag |
| `contactOwnership` | string | `Shared` / `Owned`. Returned on the group-members response |
| `createTimestamp`, `lastUpdateTimestamp` | ISO 8601 UTC | Microsecond precision, varies between 6 and 7 fractional digits |
| `addresses` | array of address objects | |
| `contactMetadata` | object | Free-form string key/value pairs |

The address object:

| Field | Type | Direction | Notes |
| --- | --- | --- | --- |
| `addressId` | GUID | response only | |
| `addressType` | string | both | `Msisdn` or `Email` going in, `MSISDN` coming back. Never compare case-sensitively |
| `addressValue` | string | both | E.164 with the leading `+` |
| `destinationCode` | string | response only | ISO 3166 alpha-2, e.g. `GB`. Derived, not settable |
| `optOutStatus` | string | both | `Subscribed` / `Unsubscribed` per address |

`smsoptOutStatus` is returned by `GET` by-id, `GET /v2/contacts/filter` and the
group-members list, but not by `POST /v2/contacts` or `PUT /v2/contacts/{id}`.
Read the contact back if the field is needed. Do not treat either field as
connected to `/v2/optouts`; see `references/opt-outs.md`.

## Body shape: single versus bulk

The single-contact writes, `POST /v2/contacts` and `PUT /v2/contacts/{contactId}`,
take `firstName`, `lastName` and the other contact fields at the top level of the
body, beside `accountReference`, with no `contacts` wrapper. The bulk endpoints
wrap the rows: `{"accountReference": ..., "contacts": [ ... ]}`. That is why the
bulk parameter tables below name fields as `contacts[].firstName` and so on.

`addressType` and `addressValue` always sit inside an `addresses` array:
`addresses: [{"addressType": ..., "addressValue": ...}]`.

## POST /v2/contacts

Create one contact. The path is `https://api.esendex.co.uk/v2/contacts`; a
trailing slash also works.

**Method:** POST. **Success:** `201 Created`.

**Headers:** `Content-Type: application/json`, `X-Api-Key`.

**Request body**

| Parameter | Type | Required | Constraint |
| --- | --- | --- | --- |
| `accountReference` | string | Required | `EXUK0000000` form |
| `firstName` | string | Required | Max 500 characters |
| `lastName` | string | Required | Max 500 characters |
| `addresses[].addressType` | string | Conditional | `Msisdn` or `Email`. Conditional on supplying an address at all |
| `addresses[].addressValue` | string | Conditional | The number or email. Conditional on supplying an address at all |
| `quickName` | string | Optional | Short name |
| `addresses[].optOutStatus` | string | Optional | `Subscribed` / `Unsubscribed` |
| `contactMetadata` | object | Optional | Free-form string key/value pairs |
| `groups` | array of GUID | Optional | Bare GUID strings. Confirmed on the bulk endpoints; test on single create before relying on it |

Minimum viable body, per the example:

```json
{
  "accountReference": "EXUK0000000",
  "firstName": "Sam",
  "lastName": "Taylor",
  "quickName": "Sam T",
  "addresses": [
    {"addressType": "Msisdn", "addressValue": "+447700900022",
     "optOutStatus": "Subscribed"}
  ],
  "contactMetadata": {"team": "octopus"}
}
```

**Response:** the created contact wrapped in `data`, with `contactId`,
`accountReference`, `firstName`, `lastName`, `quickName`, `lastUpdatedBy`,
`createTimestamp`, `lastUpdateTimestamp`, `addresses[]` (each with `addressId`
and a derived `destinationCode`) and `contactMetadata`. No `smsoptOutStatus`, and
no `optOutStatus` on the address, even though the request set one.

**Errors**

| Code | Shape | Trigger |
| --- | --- | --- |
| 400 | A | One or more required fields invalid or missing. Read `errorMessage` |
| 409 | A, `contact_already_exists` | "a record with matching contact data already exists" |
| 401 | B | Authorization header missing or invalid |

Do not try to predict a 409 from the data you hold. Search
`/v2/contacts/filter` first, or accept the 409 as the existence check.

## GET /v2/contacts/{contactId}

**Path:** `https://api.esendex.co.uk/v2/contacts/{contactId}`. **Method:** GET.
**Success:** `200 OK`. **Headers:** `X-Api-Key` only.

**Path parameter:** `contactId`, a GUID.

The response is a single contact, so there is nothing to filter, sort or page.
Send no query parameters, and use `GET /v2/contacts/filter` to filter, search or
sort.

**Response:** one contact under `data`, including `smsoptOutStatus`.

**Errors**

| Code | Shape | Trigger |
| --- | --- | --- |
| 404 | A, `contact_not_found` | The contactId does not exist or is not a valid GUID - malformed and absent are both 404 here, not 400 |
| 401 | B | Missing or invalid auth header |

## GET /v2/contacts/filter

The list and search endpoint. `GET /v2/contacts` is not a list endpoint;
`GET /v2/contacts/filter` is.

**Path:** `https://api.esendex.co.uk/v2/contacts/filter`. **Method:** GET.
**Success:** `200 OK`.

**Headers:** `X-Api-Key`, and `AccountReference`, which is required here. This is
the only contacts endpoint that requires it as a header. The cURL sample also
passes `AccountReference` as a query parameter alongside the header; sending both
is harmless.

**Query parameters**

| Parameter | Values / constraint |
| --- | --- |
| `AccountReference` | Duplicate of the header |
| `optOutStatus` | `subscribed` or `unsubscribed`. Filters the **contact** field, not `/v2/optouts` |
| `sortBy` | `Name` or `createdAt` |
| `sortOrder` | `Asc` or `Desc`. Default descending |
| `search` | Free text, matched across address, first name, last name and quick name simultaneously. It cannot be scoped to one field |
| `destination` | ISO 3166 country code, e.g. `GB`, `DE`, `IT`, `US` |
| `groupId` | GUID. The cURL writes `GroupId=Array`, marking a multi-value parameter |
| `contactOwnership` | `Shared`, `Owned` or `All`. Default `All` |
| `AddressType` | Address type. Writes use `Msisdn` / `Email`; confirm the accepted filter values before relying on it |
| `MetadataKey` | Metadata key to filter on |
| `MetadataValue` | Metadata value to filter on |
| `PageNo`, `PageSize` | `PageSize` defaults to 1 |

Test `MetadataKey` and `MetadataValue` before relying on them: check whether
`MetadataValue` matches exactly, by prefix or by substring, whether it is
case-sensitive, and whether `MetadataKey` alone means "has this key".

To filter on more than one `GroupId`, test the query-string form first
(repeated `GroupId=a&GroupId=b`, comma-joined, or bracketed `GroupId[]=`), or
make one call per group. The same `=Array` marker appears on the contact delete,
group delete and group-contact delete cURLs.

**Response**

```json
{"data": {"contacts": [ {...} ], "totalCount": 10, "totalPages": 2,
          "currentPage": 1}}
```

The array key is `contacts`. Each contact carries `addresses[].optOutStatus`
and `contactMetadata`, whose values are strings.

**Errors**

| Code | Shape | Trigger |
| --- | --- | --- |
| 400 | A | `accountReference` missing from the header or invalid |
| 401 | A, `unauthenticatedError` | Missing or invalid auth. Note: shape A here, shape B on the sibling endpoints |

A filter matching nothing is a 200 with an empty `contacts` array and
`totalCount: 0`, not a 404.

## PUT /v2/contacts/{contactId}

**Path:** `https://api.esendex.co.uk/v2/contacts/{contactId}`. **Method:** PUT.
**Success:** `200 OK`.

**Headers:** `Content-Type: application/json`, `X-Api-Key`.

**Request body**

| Parameter | Type | Required | Constraint |
| --- | --- | --- | --- |
| `accountReference` | string | Required | `EXUK0000000` form |
| `firstName` | string | Required | Max 500 characters |
| `lastName` | string | Required | Max 500 characters |
| `addresses[].addressType` | string | Conditional | `MSISDN` or `Msisdn`; case-insensitive on input |
| `addresses[].addressValue` | string | Conditional | |
| `quickName` | string | Optional | "The short name of the contact" |
| `addresses[].optOutStatus` | string | Optional | `Subscribed` / `Unsubscribed`, per address. See below |
| `contactMetadata` | object | Optional | Key/value pairs |
| `groups` | array | Optional | "If using this parameter a valid groupID must be provided" |

Write `optOutStatus` inside each `addresses[]` element. On reads the
contact-level flag has the different name `smsoptOutStatus` and the per-address
flag is `optOutStatus`. Do not assume that writing one moves the other.

Treat PUT as a full replace: a body without `contactMetadata`, `addresses` or
`quickName` may clear the stored values. Read-modify-write, and verify on one
record before running a sync.

Metadata key case is not preserved: `"additionalProp1"` can go in and come
back as `"additionalprop1"`. Match metadata keys case-insensitively.

**Response:** the updated contact under `data`, with `lastUpdateTimestamp`
advanced.

**Errors**

| Code | Shape | Trigger |
| --- | --- | --- |
| 400 | A | Required field missing or invalid |
| 404 | A, `contact_not_found` | contactId absent or not a GUID |
| 401 | B | Missing or invalid auth |

Update returns no 409, so before changing a contact's details to match another
contact's, search `/v2/contacts/filter` for the target values.

## DELETE /v2/contacts?contactId=

The id is a query parameter, not a path segment.

**Path:** `https://api.esendex.co.uk/v2/contacts?contactId=contactId`.
**Method:** DELETE. **Success:** `200 OK` with an empty body.
**Headers:** `X-Api-Key` only.

**Query parameters**

| Parameter | Type | Required | Constraint |
| --- | --- | --- | --- |
| `contactId` | GUID | Required | |

The cURL sample is `?contactId=Array`, marking a multi-value parameter. Delete
one contact at a time unless the multi-value form has been tested.

**Errors:** `401` (shape B). A delete of a non-existent or stale contactId
returns the same empty 200 as a real one, so the call cannot report whether
anything was deleted. There is no undelete.

## POST /v2/contacts/bulk

Creates new contacts only. Existing records are not updated; use the upsert
for that.

**Path:** `https://api.esendex.co.uk/v2/contacts/bulk`. **Method:** POST.
**Success:** `200 OK`, not 201, unlike the single create.

**Headers:** `Content-Type: application/json`, `X-Api-Key`.

**Request body**

| Parameter | Type | Required | Constraint |
| --- | --- | --- | --- |
| `accountReference` | string | Required | Top level, once per request |
| `contacts` | array | Required | One element per contact |
| `contacts[].firstName` | string | Required | Max 500 characters |
| `contacts[].lastName` | string | Required | Max 500 characters |
| `contacts[].addresses[].addressType` | string | Conditional | `Msisdn` / `Email` |
| `contacts[].addresses[].addressValue` | string | Conditional | |
| `contacts[].quickName` | string | Optional | Max 500 characters |
| `contacts[].addresses[].optOutStatus` | string | Optional | `Subscribed` / `Unsubscribed`, per address |
| `contacts[].contactMetadata` | object | Optional | |
| `contacts[].groups` | array of GUID | Optional | Bare GUID strings in the example: `["a56cd83a-..."]`. Not objects |

Check the shape of `groups`: the example is an array of bare GUID strings, not an
array of `{"id": ...}` objects.

Chunk large imports. A very large request risks a timeout or a 413 partway
through an import, so send about 1,000 contacts per call.

**Response**

```json
{"data": {"accountReference": "EXUK0000000",
          "contacts": [{"id": "...", "firstName": "...", "lastName": "...",
                        "quickName": "...", "addresses": [...],
                        "contactMetadata": {...},
                        "result": "success", "reasons": []}]}}
```

Per-row fields that matter:

| Field | Type | Notes |
| --- | --- | --- |
| `id` | GUID | The new contactId - named `id` here, `contactId` on every non-bulk endpoint |
| `result` | string | `"success"` for a row that succeeded |
| `reasons` | array | Empty on success. Print it verbatim on failure |

The response has no `totalCount`, no pagination and no summary counts:
there is one element per submitted row, and aggregation is the caller's job. Rows
come back without `destinationCode`, `optOutStatus`, `groups`, `smsoptOutStatus`
or timestamps, so the bulk response is not a substitute for reading a contact
back.

Treat any `result` other than success as a failed row: compare
`str(result).lower() != "success"` and print `reasons` verbatim instead of
branching on specific failure values.

**Errors**

| Code | Shape | Trigger |
| --- | --- | --- |
| 400 | A | One or more required fields invalid or missing - a whole-request rejection, distinct from per-row failure |
| 401 | B (with an extra top-level `message`) | Missing or invalid auth |

Since the endpoint does not update existing records, a row for a contact that
already exists changes nothing. If an import returns 200 and nothing changed,
this is the usual cause; use `PUT /v2/contacts/bulk` for any repeat sync.

## PUT /v2/contacts/bulk

Same path, same body and same response shape as the POST, but this endpoint
creates or updates, so use it for any repeat sync.

**Path:** `https://api.esendex.co.uk/v2/contacts/bulk`. **Method:** PUT.
**Success:** `200 OK`. **Headers:** `Content-Type: application/json`,
`X-Api-Key`. If PUT returns 405, try PATCH once as a fallback.

**Request body:** identical to `POST /v2/contacts/bulk` above, plus one field:

| Parameter | Type | Required | Constraint |
| --- | --- | --- | --- |
| `contacts[].contactsId` | GUID | Conditional | "ContactId if updating a user e.g. `68890cd2-7d9d-43c4-8fc9-8de20160e76f`" |

Note the spelling: `contactsId` here, `contactId` elsewhere, and `contactIds` on
the add-to-group call. Put it inside each `contacts[]` element, since each row
updates a different contact.

If the endpoint also matches rows without `contactsId` to existing contacts, and
it matches on address value, an upsert of a row whose number changed will create
a second contact instead of updating the first. As with the single update, an
upsert row may clear the fields it omits. Verify against one known record (write
a row with metadata, then a row without it, and read the contact back) before
running a full sync.

**Errors:** as POST bulk, 400 (shape A) and 401 (shape B). Read a contact back
after updating it by `contactsId` to confirm the change landed.

## Defensive checks

A summary of the checks in this file.

| Situation | What to do |
| --- | --- |
| Large imports | Chunk at about 1,000 contacts per call |
| Bulk row results | Treat any `result` other than `"success"` as a failure and print `reasons` verbatim |
| Updating with PUT, single or bulk | Read-modify-write, and verify on one record before a sync |
| Avoiding 409 `contact_already_exists` | Search `/v2/contacts/filter` first, or accept the 409 as the existence check |
| Updating through the bulk upsert | Write one known record and read it back before a full sync |
| Multi-value query parameters (`contactId=Array`, `GroupId=Array`) | Send one value per call unless the multi-value form has been tested |
| `/v2/optouts` versus `smsoptOutStatus` / `optOutStatus` | Treat `/v2/optouts` as authoritative. See `references/opt-outs.md` |
| `MetadataKey` / `MetadataValue` filters | Test matching and case behaviour before relying on them |
| `groups` on single create | Test before relying on it, or add members with `PUT /v2/groups/{groupId}/contacts` |
| Metadata value types | Stringify numbers, booleans and nested objects before storing |
| Deleting a contactId | Confirm the id with `GET /v2/contacts/{contactId}` first; a delete of a non-existent id is an empty 200 |
