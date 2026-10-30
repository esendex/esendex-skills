# Gotchas in full

One section per row of the Gotchas table in `SKILL.md`. Each states the behaviour and what to do.
Endpoint-by-endpoint detail is in `references/contacts.md`, `references/groups.md` and
`references/opt-outs.md`; the API reference is at https://developer.esendex.co.uk.

## Listing contacts is /v2/contacts/filter, not /v2/contacts

`GET /v2/contacts` is not a list endpoint. The list and search endpoint is
`GET /v2/contacts/filter`, which is the only contacts path that returns `{"data": {"contacts":
[...], "totalCount", "totalPages", "currentPage"}}`. `GET /v2/contacts/{contactId}` returns one
contact under `data`, with no paging fields.

Treat the by-id endpoint as taking no parameters, and send every filter and search to
`/v2/contacts/filter`. It requires `AccountReference` as a header, the only contacts endpoint
that does; the cURL sample also repeats it as a query parameter, and sending both is harmless.

## Contact delete takes contactId as a query parameter

The path is `DELETE /v2/contacts?contactId=...`, not `DELETE /v2/contacts/{contactId}`. The id
is a query parameter on this endpoint even though the get and update endpoints take it as a path
segment.

The cURL shows `?contactId=Array`, marking a multi-value parameter. Delete one contact at a time
unless the multi-value form has been tested. The same `=Array` marker appears on the group delete, group-member delete and `GroupId`
filter cURLs.

## A 200 on a bulk operation does not mean every row succeeded

Bulk is a partial-success API: the HTTP status describes the request, not the rows. Both
`POST /v2/contacts/bulk` and `PUT /v2/contacts/bulk` return 200 with one element per submitted
row in `data.contacts[]`, each carrying its own `result` and `reasons`. There are no summary
counts and no `totalCount`, so aggregation is the caller's job.

Iterate the array, count the rows whose `result` is not success, and print their `reasons`
verbatim. A 400 on these endpoints is a different thing: a whole-request rejection for a missing
or invalid required field, distinct from per-row failure.

Rows come back without `destinationCode`, `optOutStatus`, `groups`, `smsoptOutStatus` or
timestamps, and the new id is named `id`, not `contactId`, so the bulk response is not a
substitute for reading a contact back.

## Any result other than success is a failed row

Compare `str(result).lower() != "success"` instead of enumerating failure states, and print
`reasons` verbatim; do not branch on specific failure values. Because `POST /v2/contacts/bulk`
does not update existing records, a row for a contact that already exists changes nothing; this
is the usual cause when an import returns 200 and nothing changed. Use
`PUT /v2/contacts/bulk` for any resynchronisation.

## Chunk bulk calls

Do not post 50,000 rows in one call: a very large request risks a timeout or a 413 partway
through a customer's import. Chunk at about 1,000 contacts per call, and report progress per
chunk so a failure halfway is visible.

## Test an update through the bulk upsert first

`PUT /v2/contacts/bulk` takes a `contactsId` GUID - "ContactId if updating a user" - to identify
which existing contact a row updates. Put it inside each `contacts[]` element, since each row
updates a different contact. Note the spelling: `contactsId` here, `contactId` elsewhere, and
`contactIds` on the add-to-group call.

If the endpoint also matches rows without `contactsId` to existing contacts, and it matches on
address value, an upsert of a row whose number changed will create a second contact instead of
updating the first. Write one known record through the update path and read it back before
running a full sync. Use PUT; if it returns 405, try PATCH once.

## PUT on a single contact is a full replace

`PUT /v2/contacts/{contactId}` requires `firstName` and `lastName` on every call. Treat it as a
replace: fields omitted from the body, such as `contactMetadata`, `addresses` or `quickName`,
may be cleared, and the same applies to an upsert row.

Do not test this on a customer's live record. Read the contact, modify the object, put it back
whole, and verify on one record before running a sync. A partial body may clear metadata or an
address, and the response does not show that it happened.

Send `accountReference` in the body as well: it is a required field.

## contactMetadata keys come back lower-cased

`"additionalProp1"` can go in and come back as `"additionalprop1"`. Do not rely on key case
surviving a write, and match metadata keys case-insensitively when reading them back.

Stringify metadata values before storing; numbers, booleans and nested objects should be
converted to strings first. Test the matching behaviour of the `MetadataKey` and `MetadataValue`
filters on `/v2/contacts/filter` - exact, prefix and case - before relying on them.

## Checking whether a contact already exists

`POST /v2/contacts` returns 409 `contact_already_exists`, "a record with matching contact data
already exists", when it collides with an existing record. Do not try to predict a collision from
the data held.

Treat "does this contact exist?" as a search against `GET /v2/contacts/filter`, or accept the 409
as the existence check. Before renaming a contact through `PUT /v2/contacts/{contactId}`, search
for an existing contact with the same details, since update returns no 409.

## The add-contacts field is contactIds, not contactsId

`PUT /v2/groups/{groupId}/contacts` takes `{"contactIds": ["<guid>", ...]}`, an array of bare
GUID strings, not objects.

A wrong key raises no error: unknown body fields are ignored, not rejected, so the wrong key
returns 200 with an empty `groupContacts` array and no membership created. Compare the returned
`groupContacts` length against the number of ids sent. Check that each contact id belongs to a
real contact before sending, since the 400 covers GUID format only and the 404 covers the group,
and test re-adding an existing member before relying on it.

## Group delete takes groupId as a query parameter

Delete a group with `DELETE /v2/groups?groupId={id}`. The 400 error `group_ids_empty`, "At least
one group id must be specified.", is returned when the id is missing. If the query form returns
404 or 405, fall back to `DELETE /v2/groups/{groupId}`. Delete one group per call unless the
multi-value form has been tested.

Deletion is contained either way: deleting a group deletes none of its contacts, and removing
contacts from a group deletes neither the contacts nor the group. A group with zero members is
valid, so `contactsCount: 0` is not an error state.

## Reading the group-members array

`GET /v2/groups/{groupId}/contacts` returns its result under `data.contacts`. Read
`data["contacts"]` with a fallback to `data.get("groups")`, or key off `totalCount` before
touching the array, so an empty group is handled whichever key comes back. A paginator that
infers the array key by picking the first list-valued key under `data` can return nothing here
and report no error.

To tell "the group is empty" apart from "the group does not exist", confirm with
`GET /v2/groups/{groupId}`, which returns `group_not_found` for an unknown id.

## Single-contact bodies have no contacts wrapper

`POST /v2/contacts` and `PUT /v2/contacts/{contactId}` take `firstName`, `lastName` and the rest
at the top level of the body, beside `accountReference`, with no `contacts` key. Only the bulk
endpoints wrap rows, as `{"accountReference": ..., "contacts": [...]}`.

Addresses go inside an `addresses` array: `addresses: [{"addressType": ..., "addressValue":
...}]`.

## optOutStatus is written per address

Write `optOutStatus` inside each `addresses[]` element. On reads the contact-level flag is named
`smsoptOutStatus` and the per-address flag is `optOutStatus`.

Do not assume that writing one moves the other, or that either is connected to `/v2/optouts`;
treat the suppression list as authoritative. Compare the values case-insensitively: reads
return `Subscribed` and `Unsubscribed`. `smsoptOutStatus` is not in the single create and update
responses, so read the contact back if the value is needed.

## The opt-out number field has three names

| Call | Where | Name |
| --- | --- | --- |
| `POST /v2/optouts` | request body | `value` |
| `GET /v2/optouts` | query string | `Address` |
| `DELETE /v2/optouts` | query string | `Value` |
| POST and GET | response body | `value` |

A filtered read therefore sends `Address` and reads back `value`; there is no `Address` field in
any response and no `Value` parameter on the GET. Because unknown parameters are ignored and not
rejected, the wrong name returns success without doing anything: a DELETE that names the field wrongly,
or sends a number in the wrong format, returns the same 200 as a real removal while the
suppression stays in place. Verify a removal by reading back with `GET
/v2/optouts?Address=...&Channel=SMS` and confirming the record has gone.

Normalise to E.164 before writing, so `07700900410` and `+447700900410` cannot become two
records and the write side and the scrub side agree. The record's own `id` is accepted by no
endpoint: removal is by `Channel` plus `Value`, there is no read-one endpoint, and there is no
bulk add or bulk remove.

## OptOutMethod is filterable but never returned

`GET /v2/optouts` accepts `OptOutMethod` with two values: `Stop`, "has been received by a
customer replying opt out", and `Manual`, "has been added directly into the Connect platform".
A consent audit needs this distinction, since it separates a customer-initiated withdrawal from
an internal suppression.

The field is not returned on the opt-out record, from either the POST or the GET, so it can be
selected on but not read back per record. To obtain the method per number, query once with
`OptOutMethod=Stop` and once with `Manual` and tag the two result sets yourself. The list also
accepts `Address`, `Channel`, `StartTime`/`EndTime` (ISO 8601, `yyyy-MM-ddThh:mm:ssZ`, filtering
`createTimestamp`), `SortBy` and `SortOrder`; sort by `createdAt`, since an opt-out record has
no name field.

## Excel damages phone columns

Assume a CSV has been through Excel. Three failure modes:

- **Scientific notation.** `4.47701E+11` where `447700900678` was meant. The precision is gone,
  and parsing cannot recover it. `to_e164()` raises `ValueError` on it instead of coercing,
  so these rows are reported as failures. Ask for the file re-exported with the column formatted
  as text.
- **Stripped leading zeros.** `7700900123` where `07700900123` was meant. `to_e164()` handles
  this for the default dial code, but check the dial code matches the list's country or the
  import will produce valid-looking but wrong numbers.
- **Invisible characters.** Trailing whitespace, non-breaking spaces, and `(0)` mid-number.
  `to_e164()` tolerates these, along with spaces, hyphens, dots, brackets and slashes.

`to_e164()` raises `ValueError` and never returns a wrong number: on any character outside
that formatting set, on a misplaced `+`, and on a result outside the E.164 range of 8 to 15
digits. Catch it per row and record the failure, so a corrupted cell is reported as a reject and
never messaged.

Report how many rows were reformatted and how many were unparseable, and never drop a malformed
row silently: state the count and offer to import the rest.

## Deletes return 200 and cannot be undone

Contact delete, group delete and opt-out delete all return 200 with an empty body, including for
an id that does not exist. A wrong or stale id therefore gets the same response as a successful delete,
and there is no undelete. Removing a contact that is not a member of a group, and deleting an
opt-out that was never there, are likewise indistinguishable from real operations.

Before deleting anything on a user's behalf, list the affected records and state what will go.
Never infer a bulk delete from an ambiguous instruction: "get rid of the old list" is a question
to ask, not an instruction to execute. To confirm a group exists before deleting it, use
`GET /v2/groups/{groupId}`, which returns `group_not_found` for an unknown id.

## The legacy v1 XML API

The current API is JSON over REST, authenticated with an `X-Api-Key` header, on
`https://api.esendex.co.uk`, with every path under `/v2/`. An older XML-based Esendex API exists,
and its conventions do not carry over. Anything resembling a `/v1.x/` path, an
XML request or response body, or HTTP Basic auth with a username and password is the legacy
interface and does not apply to any endpoint in this skill.

The key header is `X-Api-Key`; see `esendex-setup-account`, `references/conventions.md`. Prefer
the developer docs at https://developer.esendex.co.uk over recollection whenever the two disagree.
