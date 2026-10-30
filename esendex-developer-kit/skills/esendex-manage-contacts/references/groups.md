# Group endpoints in full

Eight endpoints. A group carries a name, a description and a member count, so
most of the detail below concerns membership and the routes and field names each
call expects.

## Contents

- [Shared shapes](#shared-shapes)
- [POST /v2/groups](#post-v2groups)
- [GET /v2/groups/{groupId}](#get-v2groupsgroupid)
- [GET /v2/groups](#get-v2groups)
- [PUT /v2/groups/{groupId}](#put-v2groupsgroupid)
- [DELETE /v2/groups](#delete-v2groups)
- [PUT /v2/groups/{groupId}/contacts](#put-v2groupsgroupidcontacts)
- [GET /v2/groups/{groupId}/contacts](#get-v2groupsgroupidcontacts)
- [DELETE /v2/groups/{groupId}/contacts?contactId=](#delete-v2groupsgroupidcontactscontactid)
- [Defensive checks](#defensive-checks)


## Shared shapes

`X-Api-Key` on everything. `Content-Type: application/json` on the three
endpoints with a body. `AccountReference` as a header on the two list endpoints
(`GET /v2/groups`, `GET /v2/groups/{groupId}/contacts`) and as a body field
`accountReference` on create only. See `esendex-setup-account`,
`references/conventions.md`.

Error shapes are as elsewhere: shape A (`{"errors": [{"errorCode",
"errorMessage"}]}`) for 400/404/409, shape B (the `internalErrors` envelope) for
401. Group endpoints return named error codes (`group_not_found`,
`group_already_exists`, `group_name_empty`, `group_ids_empty`,
`group_contact_id_list_empty`), which code can branch on.

The group object, identical in the create, get, get-all and update responses:

| Field | Type | Notes |
| --- | --- | --- |
| `groupId` | GUID | |
| `accountReference` | string | |
| `name` | string | Unique per account |
| `description` | string | |
| `contactsCount` | integer | Members. `0` is valid; a group can have no members |
| `lastUpdatedBy` | GUID | |
| `createTimestamp` | ISO 8601 UTC | |
| `lastUpdateTimestamp` | ISO 8601 UTC | |

There is no members array on the group object. `contactsCount` is the only
membership information a group read returns; to list members, call
`GET /v2/groups/{groupId}/contacts`.

## POST /v2/groups

**Path:** `https://api.esendex.co.uk/v2/groups`. **Method:** POST.
**Success:** `201 Created`. **Headers:** `Content-Type: application/json`,
`X-Api-Key`.

**Request body**

| Parameter | Type | Required | Constraint |
| --- | --- | --- | --- |
| `accountReference` | string | Required | `EXUK0000000` form |
| `name` | string | Required | "The desired name for the group" |
| `description` | string | Optional | Max 500 characters |

```json
{"accountReference": "EXUK0000000", "name": "Newsletter",
 "description": "Monthly newsletter subscribers"}
```

**Response:** the created group under `data`, with `contactsCount: 0`.

**Errors**

| Code | Shape | Trigger |
| --- | --- | --- |
| 400 | A | Incorrect syntax or a missing/incorrect required property. "You should not repeat the request without modifications" |
| 409 | A, `group_already_exists` | `errorMessage`: "A group with this name already exists." |
| 401 | B | Missing or incorrect auth |

Group names are unique per `accountReference`. Check with `GET /v2/groups?name=...` before creating.

## GET /v2/groups/{groupId}

**Path:** `https://api.esendex.co.uk/v2/groups/{groupId}`. **Method:** GET.
**Success:** `200 OK`. **Headers:** `X-Api-Key` only.

**Path parameter:** `groupId`, GUID. No query parameters.

**Response:** one group object under `data`. No members.

**Errors**

| Code | Shape | Trigger |
| --- | --- | --- |
| 404 | A, `group_not_found` | "There is no group with the specified Id." Covers both absent and invalid-format ids |
| 401 | B | Missing or incorrect auth header |

## GET /v2/groups

**Path:** `https://api.esendex.co.uk/v2/groups`. **Method:** GET.
**Success:** `200 OK`. **Headers:** `X-Api-Key`, `AccountReference`.

**Query parameters**

| Parameter | Values / constraint |
| --- | --- |
| `AccountReference` | Duplicate of the required header |
| `groupId` | GUID. "Filter by groupIds" |
| `name` | Filter by group name. Test whether it matches exactly or by substring before relying on it |
| `groupOwnership` | `Shared`, `Owned` or `All`. Default `All` |
| `sortBy` | `name` or `createdAt` |
| `sortOrder` | `Asc` or `Desc`. Default descending |
| `StartTime` | Lower bound. `/v2/optouts` uses ISO 8601 `yyyy-MM-ddThh:mm:ssZ` on creation time; confirm the format and field here before relying on it |
| `EndTime` | Same, upper bound |
| `PageNo`, `PageSize` | `PageSize` defaults to 1 |

Send `name` for the uniqueness pre-check.

**Response**

```json
{"data": {"groups": [ {...}, {...} ], "totalCount": 2, "totalPages": 1,
          "currentPage": 1}}
```

Array key `groups`. An account with no groups returns 200 with `"groups": []`,
`totalCount: 0` and `totalPages: 0`. `totalPages: 0` with `currentPage: 1` means
a `currentPage <= totalPages` loop condition terminates correctly, while a
`currentPage < totalPages` one never starts.

**Errors**

| Code | Shape | Trigger |
| --- | --- | --- |
| 400 | A | Incorrect or missing required properties |
| 404 | A, `group_not_found` | Can be returned when filtering on a `groupId` that does not exist. Check `totalCount` and catch the 404 |
| 401 | B | Missing or incorrect auth |

## PUT /v2/groups/{groupId}

Renames a group and/or replaces its description. Membership is not touched.

**Path:** `https://api.esendex.co.uk/v2/groups/{groupId}`. **Method:** PUT.
**Success:** `200 OK`. **Headers:** `Content-Type: application/json`,
`X-Api-Key`.

**Request body**

| Parameter | Type | Required | Constraint |
| --- | --- | --- | --- |
| `name` | string | Required | Max 500 characters. Sending it empty is a 400 |
| `description` | string | Optional | Max 500 characters |

No `accountReference` in the body.

Send the keys in lower case, as everywhere else in the API:

```json
{"name": "updated", "description": "updated"}
```

Unknown body fields are ignored, not rejected, so a misspelt or wrongly cased key
returns 200 with no rename. Read the group back to confirm the change.

**Response:** the updated group under `data`, `lastUpdateTimestamp` advanced,
`contactsCount` unchanged.

**Errors**

| Code | Shape | Trigger |
| --- | --- | --- |
| 400 | A, `group_name_empty` | "Group name must be provided." |
| 404 | A, `group_not_found` | groupId absent, or not supplied as a GUID |
| 401 | B | Missing or incorrect auth |

Create enforces name uniqueness with `group_already_exists`, but update returns no
409, so check the target name is free with `GET /v2/groups?name=...` before
renaming.

`name` is required on every update, so treat this as a replace: omitting
`description` may clear it. Read the group first and send both fields.

## DELETE /v2/groups

Deleting a group deletes neither its contacts nor any other group those contacts
belong to.

**Path:** `https://api.esendex.co.uk/v2/groups?groupId={groupId}`.
**Method:** DELETE. **Success:** `200 OK` with an empty body.
**Headers:** `X-Api-Key` only.

The id is a query parameter. If the query form returns 404 or 405, fall back to
`DELETE /v2/groups/{groupId}`. The cURL's `?groupId=Array` marks a multi-value
parameter; delete one group per call unless the multi-value form has been
tested.

**Query parameter**

| Parameter | Type | Required | Constraint |
| --- | --- | --- | --- |
| `groupId` | GUID, or an array of GUIDs | Required | At least one must be supplied |

**Errors**

| Code | Shape | Trigger |
| --- | --- | --- |
| 400 | A, `group_ids_empty` | "At least one group id must be specified." No group id supplied, or an invalid one |
| 401 | B (with an extra top-level `message`) | Missing or invalid auth |

Deleting a groupId that does not exist returns the same empty 200 as deleting a
real one, so the call cannot confirm it deleted anything, and there is no
undelete. `GET /v2/groups/{groupId}` returns `group_not_found` for an unknown id,
so use it to confirm the group exists first.

## PUT /v2/groups/{groupId}/contacts

Adds one or more existing contacts to a group. It does not create contacts.

**Path:** `https://api.esendex.co.uk/v2/groups/{groupId}/contacts`.
**Method:** PUT. **Success:** `200 OK`. **Headers:**
`Content-Type: application/json`, `X-Api-Key`.

**Path parameter:** `groupId`, GUID.

**Request body**

| Parameter | Type | Required | Constraint |
| --- | --- | --- | --- |
| `contactIds` | array of GUID | Required | One or more contactIds. Bare GUID strings, not objects |

```json
{"contactIds": ["59152cde-77d2-414b-b616-a3a70c8f2a47"]}
```

**Response**

```json
{"data": {"groupContacts": [
  {"groupContactId": "c92fd77e-9386-429d-a240-a1c3c380c0dd",
   "groupId": "cb960734-8a57-442d-983c-92526456d3ed",
   "contactId": "ad3db3a0-9989-4ebf-b64b-d12c2c2895d0",
   "lastUpdatedBy": "907da4a7-bb93-4772-8af4-a95cc59e5a91",
   "createTimestamp": "2024-11-26T14:56:36.7986345Z"}]}}
```

Membership is a first-class record with its own id, `groupContactId`. There is no
`result`/`reasons` per row as there is on contacts bulk, and no counts, so a
partial success, if it is possible here, would show up only as a `groupContacts`
array shorter than the `contactIds` sent. Compare the lengths.

**Errors**

| Code | Shape | Trigger |
| --- | --- | --- |
| 400 | A | "an invalid or missing required property, i.e. contactId was provided in an invalid format (not GUID)" |
| 404 | A, `group_not_found` | The groupId in the path is absent or invalid |
| 401 | B | Missing or invalid auth |

The 400 covers GUID format and the 404 covers the group, so a well-formed id for
a contact that does not exist may be skipped without an error. Verify contact ids before
sending a large batch, and compare the response length. Test re-adding a contact
that is already in the group before relying on it, and check whether it returns
the existing `groupContactId`.

## GET /v2/groups/{groupId}/contacts

Lists the members of one group, with the contacts filters applied within it.

**Path:** `https://api.esendex.co.uk/v2/groups/{groupId}/contacts`.
**Method:** GET. **Success:** `200 OK`. **Headers:** `X-Api-Key`,
`AccountReference`.

**Path parameter:** `groupId`, GUID.

**Query parameters**, the same set as `GET /v2/contacts/filter`, scoped to the
group:

| Parameter | Values / constraint |
| --- | --- |
| `AccountReference` | Duplicate of the required header |
| `GroupId` | Redundant with the path segment; leave it out |
| `search` | Matches across address, first name, last name and quick name together |
| `destination` | ISO 3166 country code |
| `optOutStatus` | `subscribed` or `unsubscribed`. The contact field, not `/v2/optouts` |
| `contactOwnership` | `Shared`, `Owned`, `All`. Default `All` |
| `sortBy` | `name` |
| `sortOrder` | `Asc` / `Desc`. Default descending |
| `AddressType` | Address type |
| `MetadataKey`, `MetadataValue` | Test the matching semantics before relying on them |
| `PageNo`, `PageSize` | `PageSize` defaults to 1 |

**Response**

```json
{"data": {"contacts": [ {...} ],
          "filterOptions": {"accountReference": "{accountReference}"},
          "totalCount": 1, "totalPages": 1, "currentPage": 1}}
```

Array key `contacts`. Two things unique to this response: a `filterOptions`
object echoing the filters back, and `contactOwnership` on each contact.

Read `data["contacts"]` with a fallback to `data.get("groups")`, or key off
`totalCount` before touching the array, so an empty group is handled whichever
key comes back. A paginator that picks the first list-valued key under `data`
can return nothing here and report no error.

**Errors**

| Code | Shape | Trigger |
| --- | --- | --- |
| 400 | A | Incorrect or missing required properties |
| 401 | B | Missing or incorrect auth |

To tell "the group is empty" apart from "the group does not exist", confirm the
group exists with `GET /v2/groups/{groupId}`.

## DELETE /v2/groups/{groupId}/contacts?contactId=

Removes members. It deletes neither the contact records nor the group: "A group
can still exist with no associated contacts."

**Path:**
`https://api.esendex.co.uk/v2/groups/{groupId}/contacts?contactId={contactId}`.
**Method:** DELETE. **Success:** `200 OK` with an empty body.
**Headers:** `X-Api-Key` only.

**Path parameter:** `groupId`, GUID.

**Query parameter**

| Parameter | Type | Required | Constraint |
| --- | --- | --- | --- |
| `contactId` | GUID | Required | One or more contacts to remove from a single group, in the query string |

The cURL shows `?contactId=Array`, marking a multi-value parameter. Remove one at
a time unless the multi-value form has been tested.

**Errors**

| Code | Shape | Trigger |
| --- | --- | --- |
| 400 | A, `group_contact_id_list_empty` | "At least one group contactId must be specified." Also covers an invalid contactId |
| 404 | A, `group_not_found` | The groupId is absent or invalid |
| 401 | B (with an extra top-level `message`) | Missing or invalid auth |

Removing a contact that is not a member of this group returns the same empty 200
as a real removal. List the members first if you need to confirm what was
removed.

## Defensive checks

| Situation | What to do |
| --- | --- |
| Deleting a group | `DELETE /v2/groups?groupId=...`; fall back to the path form on a 404 or 405 |
| Passing several ids (`groupId=Array`, `contactId=Array`) | One id per call unless the multi-value form has been tested |
| Renaming a group | Check the target name is free with `GET /v2/groups?name=...` first |
| Updating a group | Read it first and send both `name` and `description` |
| Re-adding an existing member | Test before relying on it |
| Adding contacts | Verify the contact ids exist, then compare the `groupContacts` length with the ids sent |
| Large add-to-group calls | Chunk the ids, as for contacts bulk |
| An empty members list | Confirm the group exists with `GET /v2/groups/{groupId}` |
| Removing a member or deleting a group | Read first; the empty 200 does not confirm anything was removed |
| Filtering groups by `name` | Test exact versus substring matching before relying on it |
