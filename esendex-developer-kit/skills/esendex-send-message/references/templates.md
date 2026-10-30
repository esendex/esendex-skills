# Reference: /v2/templates

All nine template endpoints with their exact bodies.

Headers throughout: `X-Api-Key`, `AccountReference`, and `Content-Type:
application/json` on writes. Send `Content-Type` on lock and unlock too, even though they
take no body.

## Endpoint map

| Operation | Call | Success | Response body |
| --- | --- | --- | --- |
| Create | `POST /v2/templates` | 201 | `data.id` |
| Get one | `GET /v2/templates/{templateId}` | 200 | full template |
| List | `GET /v2/templates` | 200 | `data.templates[]`, `totalCount`, `currentPage`, `totalPages` |
| Update | `PUT /v2/templates/{templateId}` | 204 | none |
| Delete | `DELETE /v2/templates/{templateId}` | 204 | none |
| Lock | `PATCH /v2/templates/{templateId}/lock` | 204 | none |
| Unlock | `PATCH /v2/templates/{templateId}/unlock` | 204 | none |
| Change tags | `PATCH /v2/templates/{templateId}/tags` | 204 | none |
| Copy to sub-account | `POST /v2/templates/{templateId}/copy` | 201 | `data.id` |

A 204 is the success signal on five of these. Do not attempt to parse a body.

## Create / Update body

Both take the same shape. Create is `POST` to the collection; update is a full `PUT`.

| Parameter | Type | Req | Notes |
| --- | --- | --- | --- |
| `name` | String | Required | Template name |
| `templateType` | String | Required | Only `Text` is currently accepted |
| `messageType` | String | Required | Enum below |
| `channelSettings` | Object | Required | Per-channel configuration wrapper |
| `channelSettings.sms` | Object | Required | SMS-specific settings |
| `channelSettings.sms.characterSet` | String | Optional | `Auto` \| `GSM` \| `Unicode`, default `Auto` |
| `content` | String | Required | The message body. Square-bracket variables and `[shorten:...]` both work here |

`messageType` enum for templates, including the two extra values the send endpoint does
not list: `Unknown`, `MarketingAndResearch`, `NotificationsAndReminders`,
`AuthenticationAndSecurity`, `PaymentsAndCollections`, `InternalOperations`,
`CustomerSupport`, `Conversational`, `BlueLight`.

On update, send the complete object with all five required fields: `PUT` semantics
make a partial body risky. On templates, the `[shorten:...]` marker goes in `content`;
there is no `body.text` on this endpoint.

## Read shape is not write shape

| You send | You get back |
| --- | --- |
| `templateType: "Text"` | `type: "Text"` |
| `channelSettings: {"sms": {"characterSet": "Auto"}}` | `channelSettings: [{"channel": "Sms", "settings": "{\"CharacterSet\":\"Auto\"}"}]` |

`settings` is a JSON-encoded string inside an array, and its inner key is PascalCase
`CharacterSet`. A GET response cannot be fed straight back into a PUT; rebuild the
request shape.

```python
import json
t = ex.get(f"/v2/templates/{template_id}")["data"]
sms = next((c for c in t.get("channelSettings", []) if c.get("channel", "").lower() == "sms"), None)
charset = json.loads(sms["settings"]).get("CharacterSet") if sms else None
```

Full read response fields: `id`, `createTimestamp`, `lastUpdateTimestamp`, `name`,
`content`, `accountReference`, `createdBy`, `lastUpdatedBy`, `type`, `messageType`,
`channelSettings[]`, `variables[]`, `isLocked`, `tags[]`.

Send one live test through any new template before a bulk run, to confirm its variables
render as expected and to see what happens when a recipient lacks one.

## List query parameters

| Parameter | Notes |
| --- | --- |
| `PageSize` | 1–1000. Default 1 - always set it, or you will read one row and conclude the account is empty |
| `PageNo` | 1+, default 1 |
| `sortBy` | `name` \| `createdAt` |
| `sortOrder` | `Asc` \| `Desc`, default descending |
| `CreatedStartDate` | Creation date lower bound |
| `CreatedEndDate` | Creation date upper bound |
| `Search` | Test its behaviour on a known template before relying on it |
| `Tags`, `Channel`, `TemplateType` | Further filters. `Tags` is the only route to tag filtering, so test it on a small set before relying on it |

`ex.paginate("/v2/templates", key="templates")` handles the paging.

## Tags

The tags endpoint takes a `tagIds` array:

```python
ex.patch(f"/v2/templates/{template_id}/tags", {"tagIds": ["ba3febff-8626-4e3a-9a2f-4579b516631f"]})
```

Tags are referenced by GUID, never by name. This skill covers no endpoint to create,
list, rename or delete a tag, so treat tags as portal-managed. If a user wants templates
tagged programmatically, `tagIds` can be set, but they must supply the ids from the
portal first.

`PATCH` takes a full array, so assume it replaces the tag set and that an empty array
clears it; verify both on a throwaway template.

## Lock and unlock

Locking prevents editing. `isLocked` reports the current state.

Four behaviours need confirming before anyone relies on them: whether a locked template
can still be used to send, whether lock blocks delete or tag changes, what error a write
to a locked template returns, and who may unlock. If a user is treating lock as a governance
control, have them verify enforcement on a throwaway template.

Related permissions note: a "Template user" can send using predefined
templates and view the inbox and sent items, but cannot create, manage or delete
templates or reach any other settings. On accounts that use this role, templates are
how those users send.

## Copy to a sub-account

```python
ex.post(f"/v2/templates/{template_id}/copy", {"destination": "EXUK0000001"})
```

`destination` is an account reference, not a GUID, and must be a sub-account directly
associated with the parent. This is the mechanism for pushing compliance-approved
wording to every sub-account instead of recreating it by hand.

Check that a new `data.id` came back before reporting success.

## Delete

`DELETE /v2/templates/{templateId}` → 204. Irreversible, no version history.

Before deleting on a user's behalf, check for delayed or throttle schedules that
reference the `templateId` and confirm with the user. Test whether a locked template
can be deleted before relying on the lock to prevent it.

## Error codes

| Status | Where | Code |
| --- | --- | --- |
| 400 | all writes | `{"errors":[{"errorCode","errorMessage"}]}` |
| 401 | all | `unauthenticatedError` |
| 404 | get / update / delete / lock / unlock / tags | `template_not_found` - "A template with the given id does not exist" |
