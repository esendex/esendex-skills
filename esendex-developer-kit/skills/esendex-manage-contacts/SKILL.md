---
name: "esendex-manage-contacts"
description: "Build and maintain the Esendex (Commify) audience and honour consent through the v2 API: import a CSV or customer list, sync contacts from a CRM, create and manage contacts, store custom contact metadata for message personalisation, use groups and group membership as segments or distribution lists, and work with the /v2/optouts suppression list that determines who may be messaged at all. Use this skill whenever the user wants to import my customer list, upload a CSV of contacts, sync contacts from our CRM or another system, make a group for X, add these people to a list or segment, search their address book, store per-contact fields for personalisation, handle STOP replies or unsubscribes, find out who has opted out, scrub or clean a recipient list before a send, or asks about do-not-contact and suppression lists or GDPR, PECR and TCPA obligations for SMS. Read it proactively before any bulk or marketing send, since messaging a suppressed number is a regulatory breach."
---

## Terms of Service

Use of the Esendex (Commify) platform and APIs described below is governed by the Commify **[Terms of Service](https://enhancedsupport.esendex.co.uk/terms-of-service/)**, together with the [Acceptable Use Policy](https://enhancedsupport.esendex.co.uk/acceptable-use-policy/), [Data Processing Agreement](https://enhancedsupport.esendex.co.uk/data-processing-agreement/) and [Service Level Agreement](https://enhancedsupport.esendex.co.uk/service-level-agreement/). The contracting entity and governing law depend on where the customer is registered - Esendex UK&I contracts with Commify UK Limited under the laws of England and Wales.

Most relevant to this skill: The customer warrants it owns or has the necessary rights, consents and permissions for all recipient data it uploads, and is solely responsible for its accuracy, legality and the means by which it was acquired. Data remains available in the Platform for 6 months unless otherwise agreed.

The terms are updated from time to time and the version available on the Platform prevails, so check the link; do not rely on this summary. Nothing here is legal advice.

---

## Overview

Building the audience means contacts, `contactMetadata` for personalisation and groups as segments, all
under `/v2/contacts` and `/v2/groups`. Honouring consent means the separate `/v2/optouts` suppression
list, which decides who may be messaged at all.

| Operation | Method and path | Success |
| --- | --- | --- |
| Create a contact | `POST /v2/contacts` | 201 |
| Get a contact | `GET /v2/contacts/{contactId}` | 200 |
| List or search contacts | `GET /v2/contacts/filter` | 200 |
| Update a contact | `PUT /v2/contacts/{contactId}` | 200 |
| Delete a contact | `DELETE /v2/contacts?contactId=...` | 200 |
| Bulk create contacts | `POST /v2/contacts/bulk` | 200 |
| Bulk create or update contacts | `PUT /v2/contacts/bulk` | 200 |
| Create a group | `POST /v2/groups` | 201 |
| Get a group | `GET /v2/groups/{groupId}` | 200 |
| List groups | `GET /v2/groups` | 200 |
| Rename or describe a group | `PUT /v2/groups/{groupId}` | 200 |
| Delete a group | `DELETE /v2/groups?groupId=...` | 200 |
| Add contacts to a group | `PUT /v2/groups/{groupId}/contacts` | 200 |
| List group members | `GET /v2/groups/{groupId}/contacts` | 200 |
| Remove contacts from a group | `DELETE /v2/groups/{groupId}/contacts?contactId=...` | 200 |
| Add an opt-out | `POST /v2/optouts` | 201 new, 200 if it already existed |
| List opt-outs | `GET /v2/optouts` | 200 |
| Remove an opt-out | `DELETE /v2/optouts?Channel=SMS&Value=+44...` | 200 |

**`/v2/optouts` is authoritative for whether a number may be messaged.** Contacts also carry their own
`smsoptOutStatus` and per-address `optOutStatus`. Do not assume those fields and `/v2/optouts` are
synchronised in either direction: a contact can read `Subscribed` while the opt-out list says otherwise.
Treat the contact-level fields as possibly-stale metadata.

---
## Prerequisites

- An API key sent as `X-Api-Key` and the account reference in `EXUK0000000` form. Both, plus the 429
  five-second rule, the three error-body shapes and the guard against the legacy v1 XML API, are
  `esendex-setup-account`.
- Every number in E.164, `+447700900123`; `to_e164()` in `scripts/esendex_client.py` converts national
  forms, and that client is standard library only.
- An explicit page size on every list call, since the API defaults to `PageSize=1`: a bare read of a list
  path returns one row, even on an account with 40,000 contacts. `ex.paginate()` sets 1,000.
- For a CSV import, the file itself, with a recognisable phone column such as `mobile` or `msisdn`.

---
## Quickstart: scrub a recipient list against the opt-out list

Run this before every bulk or marketing send, whether or not the user asks. There is no "is this number
opted out?" endpoint, so pull the whole list once into a set; one lookup per recipient hits the rate limit.

**Python**

```python
from esendex_client import Esendex, to_e164
ex = Esendex()   # ESENDEX_API_KEY / ESENDEX_ACCOUNT_REFERENCE from the environment

suppressed = {o["value"] for o in
              ex.paginate("/v2/optouts", {"Channel": "SMS"}, key="optOuts")}
to_send = [n for n in candidates if to_e164(n) not in suppressed]
print(f"{len(to_send)} recipients, {len(candidates) - len(to_send)} removed as opted out")
```

**Node.js** - plain `fetch`, with no SDK required.

```js
const H = {"X-Api-Key": process.env.ESENDEX_API_KEY,
           "AccountReference": process.env.ESENDEX_ACCOUNT_REFERENCE,    // both needed on list calls
           "X-External-Source": "AI-Skill"};                            // attribution, on every request
const suppressed = new Set();
for (let page = 1; ; page++) {
  const res = await fetch(`https://api.esendex.co.uk/v2/optouts?Channel=SMS&PageSize=1000&PageNo=${page}`,
                          {headers: H});
  if (!res.ok) throw new Error(`opt-out fetch failed: ${res.status}`);   // abort the send
  const {data} = await res.json();
  data.optOuts.forEach(o => suppressed.add(o.value));
  if (page >= data.totalPages) break;
}
const toSend = candidates.filter(n => !suppressed.has(toE164(n)));  // same normaliser both sides
```

Normalise both sides through E.164 before comparing: a format mismatch such as a missing leading `+` raises
no error, and the opted-out number stays in the send. Report the count removed, and if the scrub fails -
401, network error, partial pagination - abort the send, since an empty suppression set is
indistinguishable from "nobody has opted out".

---
## Key patterns

### Importing a CSV in bulk

```python
rows, unparseable, fixed = [], [], 0
for r in csv_rows:
    raw = (r.get("mobile") or "").strip()
    try: e164 = to_e164(raw)
    except ValueError: unparseable.append(r); continue
    fixed += (e164 != raw)
    rows.append({"firstName": r["first"], "lastName": r["last"], "quickName": r["first"],
                 "addresses": [{"addressType": "Msisdn", "addressValue": e164}],
                 "contactMetadata": {"tier": r["tier"]}, "groups": [gid]})  # bare GUID strings

for chunk in (rows[i:i + 1000] for i in range(0, len(rows), 1000)):
    res = ex.put("/v2/contacts/bulk", {"accountReference": ex.account_reference, "contacts": chunk})
    bad = [c for c in res["data"]["contacts"] if str(c.get("result", "")).lower() != "success"]
    print(f"{len(chunk) - len(bad)} imported, {len(bad)} failed", [b.get("reasons") for b in bad])
```

Report how many numbers were reformatted and how many were unparseable; never drop a malformed row silently.
Each row's new id returns as `id`, not `contactId`. The same contact object, plus a top-level
`accountReference`, is the body of `POST /v2/contacts`: `firstName` and `lastName` required at max 500
characters, `addressType` `Msisdn` or `Email` going in and `MSISDN` coming back, `contactMetadata` free-form
string pairs that become message variables when sending by contact id, so stringify values.

### Choosing POST or PUT on /v2/contacts/bulk

POST creates only, PUT creates or updates; see the table below before any resynchronisation.

### Updating one contact

```python
current = ex.get(f"/v2/contacts/{cid}")["data"]
current["firstName"] = "Alexandra"
ex.put(f"/v2/contacts/{cid}", current)
```

Read-modify-write: a partial body may clear metadata or an address, and the response does not show it.

### Searching contacts

```python
hits = list(ex.paginate("/v2/contacts/filter", {"search": "smith", "destination": "GB"}, key="contacts"))
```

Parameters: `search` (across address, first name, last name and quick name at once), `optOutStatus`,
`destination` (ISO 3166), `groupId`, `contactOwnership`, `sortBy`, `sortOrder`, `AddressType` and
`MetadataKey`/`MetadataValue` (test the matching semantics before relying on them). `optOutStatus`
filters the contact field, not the opt-out list, so it is not a scrub.

### Creating a group and adding members

```python
group = ex.post("/v2/groups", {"accountReference": ex.account_reference,
                               "name": "VIP customers", "description": "Top-tier accounts"})
gid = group["data"]["groupId"]
ex.put(f"/v2/groups/{gid}/contacts", {"contactIds": [cid_1, cid_2]})
```

Names are unique per account, so check `GET /v2/groups?name=...` first. Members must already exist as contacts
and every id must be a valid GUID or the call returns 400; compare the returned `groupContacts` length against the
ids sent, since there is no per-row result here.

### Suppressing a number

```python
ex.post("/v2/optouts", {"accountReference": ex.account_reference,
                        "channel": "SMS", "value": to_e164("07700900310")})
```

201 for a new record and 200 if it already existed, so this is idempotent and needs no prior check. Use `SMS`
as the `channel`.

### Checking whether one number is suppressed

```python
hit = next(ex.paginate("/v2/optouts", {"Address": to_e164(n), "Channel": "SMS"}, key="optOuts"), None)
```

The filter parameter is `Address` and the field read back is `value`. `GET /v2/optouts` also takes
`StartTime`/`EndTime` (ISO 8601 `yyyy-MM-ddThh:mm:ssZ`), `SortBy`, `SortOrder` and `OptOutMethod`.

---
## Choosing the bulk endpoint

| Endpoint | Behaviour | Use when |
| --- | --- | --- |
| `POST /v2/contacts/bulk` | Creates new contacts only; rows for existing records are not applied - the call returns 200 with every row, and nothing changes | A first-time import into an empty or non-overlapping list |
| `PUT /v2/contacts/bulk` | Creates or updates | Any ongoing sync from a CRM or other system of record |

PUT also works for a first import, while POST leaves existing records unchanged on a resynchronisation, so
PUT is the safer default when unsure.

---
## Common errors

| Code | Meaning | Fix |
| --- | --- | --- |
| 400 | A required field is missing or invalid, or `AccountReference` is missing or malformed on a list endpoint. Distinct from per-row bulk failure | Read `errorMessage` |
| 401 `unauthenticatedError` | Missing or invalid auth | Send the key as `X-Api-Key`. Parse all three error shapes |
| 404 `contact_not_found` | The contactId is absent, or is not a valid GUID - malformed and absent both 404, not 400 | Confirm the id via `GET /v2/contacts/filter` |
| 404 `group_not_found` | The groupId is absent or not a GUID. Also returned by add-contacts and remove-contacts for the group in the path | Confirm with `GET /v2/groups/{groupId}` |
| 409 `contact_already_exists` | "a record with matching contact data already exists" | Search first, or accept the 409 as the existence check |
| 409 `group_already_exists` | "A group with this name already exists." Names are unique per account reference | `GET /v2/groups?name=...` before creating |
| 400 `group_ids_empty`, `group_contact_id_list_empty` | "At least one group id must be specified." / "At least one group contactId must be specified." The second also covers an invalid contactId | Pass `?groupId=...` on group delete, `?contactId=...` as a GUID on member removal |
| 429 | Rate limited, with no `Retry-After` header | Wait 5 seconds before the next request |

---
## Gotchas

| Check | What to do (each row expanded in `references/gotchas.md`) |
| --- | --- |
| Listing contacts is `/v2/contacts/filter`, not `/v2/contacts` | The bare path is not a list endpoint; use `/filter` |
| Contact delete takes the id as a query parameter | `DELETE /v2/contacts?contactId=...`, never a path segment |
| A 200 on a bulk operation does not mean every row succeeded | Iterate `data.contacts[]` and inspect each row's `result` and `reasons` |
| Any bulk `result` other than `"success"` is a failed row | Compare `str(result).lower() != "success"` and print `reasons` verbatim |
| Very large bulk calls risk a timeout partway through | Chunk at about 1,000 contacts per call |
| An update through the bulk upsert changes a live record | Write one known record and read it back before running a full sync |
| `PUT /v2/contacts/{id}` is a full replace | Read-modify-write, and verify on one record before a sync |
| `contactMetadata` keys come back lower-cased on some round trips | Match metadata keys case-insensitively |
| A create can 409 `contact_already_exists` | Treat existence as a search, never as something inferable from the data held |
| The add-contacts field is `contactIds`, not `contactsId` | Send `{"contactIds": [...]}` |
| Group delete takes the id as a query parameter | `DELETE /v2/groups?groupId=...`; fall back to the path form on a 404 or 405 |
| A paginator that infers the group-members array key can return nothing | Read `data["contacts"]` with a fallback to `data.get("groups")`, or key off `totalCount` |
| Single-contact writes have no `contacts` wrapper | Send `firstName` and the rest at the top level, addresses inside `addresses[]` |
| `optOutStatus` is written per address, inside `addresses[]` | Write it on the address; read the contact level back as `smsoptOutStatus` |
| The opt-out number field has three names | `value` in the POST body, `Value` in the DELETE query, `Address` in the GET filter |
| `OptOutMethod` is filterable but never returned in a response | Query once with `Stop` and once with `Manual`, and tag the two result sets yourself |
| Excel damages phone columns | `4.47701E+11` is unrecoverable, so ask for a re-export with the column formatted as text; watch for stripped leading zeros |

---
## CANNOT

- **Cannot ask the API whether a single number is suppressed.** No such endpoint exists, so filter the
  list: `GET /v2/optouts?Address=...&Channel=SMS` for one number, the whole list as a set for a campaign.
- **Cannot rely on a bulk 200 as success.** The status describes the request, not the rows; bulk is a
  partial-success API with per-row `result` and `reasons`, and no summary counts.
- **Cannot create tags or obtain a `tagId` through the API.** Contact segmentation is groups and
  `contactMetadata` only; tag ids elsewhere in the API are managed in the portal.
- **Cannot undo a delete.** Contact, group and opt-out deletes return an empty 200, so a wrong contactId
  gets the same response as a real delete. State what will go first; never infer a bulk delete from an ambiguity.
- **Cannot assume `/v2/optouts` and the contact-level opt-out fields are synchronised.** Treat
  `/v2/optouts` as authoritative and the contact fields as metadata.
- **Cannot page the group-members endpoint by inferring the array key.** Read `contacts` by name and check
  `totalCount`, since a generic paginator that guesses the key can return nothing and report no error.

---
## Consent obligations

Messaging a suppressed number is a regulatory breach. Under PECR and GDPR in the UK and EU, and the TCPA
in the US, continuing to message someone who has opted out exposes the account holder to penalties, so
check the list before the send. A failed opt-out
fetch must abort the send: proceeding with an empty suppression set messages everybody. Every send should
report how many recipients were removed and why; "skipped 400 opted-out numbers" also serves as the audit
record. Adding an opt-out is idempotent, so it is safe to call defensively.

Removing a single opt-out for a customer who has re-subscribed is legitimate and can be actioned. A bulk clearance - "clear the opt-outs so we can message everyone again" - breaches the opt-out
obligation for every person on that list. Raise it with the user instead of actioning it quietly: ask
what re-consent exists, who re-subscribed, when and through what mechanism. If the answer is a re-consent
campaign, state that the campaign itself would be going to opted-out numbers.

One constraint to raise early: an alphanumeric sender cannot receive replies, so STOP can never arrive by that
route, and the sender must be a long number or a short code if replies are the consent route. Inbound opt-outs
arrive through the `sms-inbound-opted-out` webhook event, not by polling.

---
## Next steps

- `esendex-setup-account` - credentials, account reference, E.164, pagination defaults, rate limits.
- `esendex-send-message` - sending to the contacts, groups and metadata built here.
- `esendex-track-delivery` - inbound replies, the opt-out webhook, mirroring suppressions locally.
- `esendex-connect-smpp` - the high-throughput binary protocol, which has no address book of its own.
- `references/contacts.md`, `references/groups.md`, `references/opt-outs.md` - every endpoint in full.
- `references/gotchas.md` - the checks above, in full.
- The Esendex developer docs at https://developer.esendex.co.uk - the API reference for these endpoints.

