# Reference: /v2/schedules/delayed and /v2/throttle-schedule

Exhaustive parameter detail for both schedule types.

Headers throughout: `X-Api-Key`, `AccountReference`, `Content-Type: application/json`
on writes.

## Time formats

The platform operates in UTC exclusively. There is no timezone field anywhere.

| Where | Format | Example |
| --- | --- | --- |
| `scheduleInformation.sendTime` | ISO 8601 with `Z` | `2026-08-03T08:00:00.000Z` |
| Throttle `startDate` / `endDate` | `YYYY-MM-DD` | `2026-08-03` |
| Throttle `timeSlotStart` / `timeSlotEnd` | `HH:MM:SS` | `08:00:00` |
| Delayed list filters | ISO 8601 with `Z` | as above |

---

# Delayed schedules

| Operation | Call | Success | Response |
| --- | --- | --- | --- |
| Create | `POST /v2/schedules/delayed` | 201 | `data.scheduleId`, `data.validationResult` |
| List | `GET /v2/schedules/delayed` | 200 | `data.pageIndex`, `pageSize`, `count`, `items[]` |
| Get one | `GET /v2/schedules/delayed/{scheduleId}` | 200 | full schedule |
| Change send time | `PATCH /v2/schedules/delayed/{scheduleId}` | 200 | `data.scheduleId` |
| Cancel | `DELETE /v2/schedules/delayed/{scheduleId}` | 200 | `data.scheduleId` |

## Create body

| Parameter | Type | Req | Notes |
| --- | --- | --- | --- |
| `scheduleInformation` | Object | Required | When the send fires |
| `scheduleInformation.sendTime` | String | Required | ISO 8601 UTC |
| `scheduleInformation.frequency` | String | Conditional | Required only for a repeat. `Daily` \| `Weekly` \| `Monthly` \| `Annually` \| `Weekdays` \| `Weekends` |
| `scheduleInformation.repeatTimes` | String/Int | Conditional | Required when `frequency` is set. Omit it with a frequency set and the schedule repeats indefinitely. `repeatTimes` without `frequency` errors. Omit both for a one-off |
| `dispatch` | Object | Required | The message |
| `dispatch.channel` | String | Required | `SMS` |
| `dispatch.from` | String | Conditional | Sender; same rules as an immediate send |
| `dispatch.body` | Object | Required | Exactly one of `text` or `templateId` |
| `dispatch.body.text` | String | Conditional | Square-bracket variables, `[shorten:...]` |
| `dispatch.body.templateId` | GUID | Conditional | Mutually exclusive with `text` |
| `dispatch.characterSet` | String | Optional | `Auto` \| `GSM` \| `Unicode` |
| `dispatch.messageType` | String | Optional | Same enum as an immediate send |
| `dispatch.name` | String | Optional | Friendly label, and the only other thing `PATCH` can change |
| `dispatch.metaData` | Object | Optional | key/value, returned on export |
| `recipients[]` | Array | Conditional | `msisdn` (E.164), `variables`, `metaData`. 1–50,000 |
| `contacts[]` | Array | Conditional | Top level, each with `contactId` |
| `groups[]` | Array | Conditional | Top level, `groupId` |

A delayed create takes top-level `contacts[]` and `groups[]`, not the `addressBook`
object used by `POST /v2/messages`; verify with one small schedule. Keep contact ids at
or below 10,000 per request.

## 201 does not mean valid

The create response carries `data.validationResult`:

```json
{"data": {"scheduleId": "...", "validationResult": {
  "isValid": true,
  "errors": [{"propertyName": "", "errorMessage": "", "attemptedValue": "",
              "customState": "", "severity": "Error", "errorCode": "",
              "formattedMessagePlaceholderValues": {}}],
  "ruleSetsExecuted": []}}}
```

Check `isValid` on every create, or success will be reported on a schedule that never
fires.

## Read response fields

`data.scheduleInformation`: `id`, `createdAt`, `accountReference`, `userId`, `name`,
`sendTime`, `frequency`, `repeatTimes`, `status`, `parentId`, `failureReason`.
`data.dispatch`: `name`, `characterSet`, `channel`, `from`, `messageType`,
`body{text, templateId}`, `metaData`.
`data.recipients[]`: `id`, `msisdn`, `variables`, `metaData`.

`name` appears inside `scheduleInformation` on the single-get response but is absent
from the same object on the list response. Repeat occurrences link to the original via
`parentId`.

## List query parameters

| Parameter | Notes |
| --- | --- |
| `DispatchName` | Filter by dispatch name |
| `StartCreatedDateTime` | Created-at lower bound |
| `StartSendDateTime` | Scheduled send lower bound |
| `EndSendDateTime` | Scheduled send upper bound |
| `StatusFilter` | Array. `Success` \| `Scheduled` \| `Canceled` \| `Failed` \| `Pending` |
| `Msisdns` | Array of recipient numbers |
| `OrderBy` | Sort field |
| `EndCreatedDateTime`, `Channel`, `OrderDir`, `PageNumber`, `PageSize` | Further filters and paging. Always set `PageSize`, since the platform default is 1 |

The delayed statuses (`Success`/`Scheduled`/`Canceled`/`Failed`/`Pending`, with
`Canceled` spelled with one l) are a different set from the throttle statuses below,
which spell it `Cancelled`.

## PATCH - what it can and cannot change

Body: `scheduleInformation.sendTime` (required) and `dispatch.name` (optional). That is
the entire surface. Body text, recipients, sender and frequency cannot be changed;
cancel and recreate instead.

Updates must land at least 5 minutes before the scheduled send time. Inside that
window the request fails or does not take effect.

404 on PATCH returns `update_schedule_not_found` / "Schedule update request not found."

## DELETE

Cancels the schedule; returns 200 with `data.scheduleId`. Requires the `scheduleId`
specifically: a `requestId` or `messageId` will fail, they are different identifiers.
404 returns the same `update_schedule_not_found` code.

---

# Throttle schedules

| Operation | Call | Success | Response |
| --- | --- | --- | --- |
| Create | `POST /v2/throttle-schedule` | 201 | `throttleScheduleId`, `estimatedEndDateTime`, `numberOfRecipients` |
| List | `GET /v2/throttle-schedule` | 200 | paged `items[]` |
| Get one | `GET /v2/throttle-schedule/{id}` | 200 | full schedule |
| Edit | `PATCH /v2/throttle-schedule/{id}` | 200 | `throttleScheduleId`, `estimatedEndDateTime`, `estimatedRateOfSend`, `numberOfRecipients` |
| Pause | `POST /v2/throttle-schedule/{id}/pause` | 204 | none |
| Resume | `POST /v2/throttle-schedule/{id}/resume` | 200 | as PATCH |
| Cancel | `DELETE /v2/throttle-schedule/{id}` | 204 | none |
| Add recipients | `POST /v2/throttle-schedule/{id}/recipients` | 201 | as PATCH |
| Get unsent | `GET /v2/throttle-schedule/{id}/unsent` | 200 | `recipients[]`, `contacts[]` |

Pause returns 204 with no body, while resume returns 200 with a body.

## Create body

| Parameter | Type | Req | Notes |
| --- | --- | --- | --- |
| `throttleScheduleInformation` | Object | Required | |
| `.startDate` | String | Required | `YYYY-MM-DD` |
| `.timeSlotStart` | String | Required | `HH:MM:SS` UTC |
| `.rateOfSend` | Integer | Conditional | Messages per hour. Required for a rate-based schedule |
| `.endDate` | String | Conditional | `YYYY-MM-DD`. Required for a period-based schedule |
| `.timeSlotEnd` | String | Conditional | `HH:MM:SS` UTC. Required for a period-based schedule |
| `.daysOfWeek` | Array | Optional | `Sunday`…`Saturday` |
| `dispatch` | Object | Required | Same shape as a delayed schedule's `dispatch` |
| `recipients[]` | Array | Conditional | `msisdn`, `variables`, `metaData` |
| `contacts[]` | Array | Conditional | `contactId` |
| `metaData` | Object | Optional | Request-level key/value |

Supply either `rateOfSend` or `endDate` + `timeSlotEnd`: "one of end date of the
throttle or the rate of send must be provided".

### Confirming the rate

Read back the rate the API echoes; do not assume the requested rate was accepted.

Throttling operates within the account's normal API rate-limiting policy
(`esendex-setup-account`) and does not raise those limits.

## Lifecycle and state constraints

Statuses: `Active`, `Paused`, `Cancelled`, `Failed`, `Completed`, `PartiallyCompleted`.

Transitions: `Active` → `Paused` → `Active`; `Active`/`Paused` → `Cancelled`.
`Completed`, `PartiallyCompleted` and `Failed` are terminal.

- Only `Paused` schedules can be resumed.
- Only `Active` or `Paused` schedules can be cancelled.
- Recipients can be added only while `Active` or `Paused`.
- Once every message has been accepted by the platform, the schedule is no longer
  editable at all.

Resume recalculates `estimatedEndDateTime` and `estimatedRateOfSend`; the ETA shifts
because the remaining recipients are re-spread from now.

`PATCH` also accepts `status: "Paused"` / `"Active"`, but the dedicated pause and
resume endpoints are simpler, so prefer them.

## Edit body

Optional only: `throttleScheduleInformation.endDate`, `.timeSlotStart`, `.timeSlotEnd`,
`.rateOfSend`, `.daysOfWeek`, `status`, and `dispatch.name`. The message body,
recipients and sender are not editable.

## Add recipients

```python
ex.post(f"/v2/throttle-schedule/{tid}/recipients", {
    "recipients": [{"msisdn": "+447700900002", "variables": {"firstName": "Sam"}}],
})
```

The body takes `recipients[]` with `msisdn`/`variables`/`metaData`, and
`contacts[].contactId`. Note the slash in `/v2/throttle-schedule/{id}/recipients`.

Adding recipients pushes out `estimatedEndDateTime` on a rate-based schedule.

## Unsent recovery

`GET /v2/throttle-schedule/{id}/unsent` returns intended destinations that never
received a message. Only populated when the schedule is `PartiallyCompleted`,
`Cancelled` or `Failed`. Returns 404 when the id doesn't exist or is malformed.

The payload is shaped like a request body (`recipients[]` with
`msisdn`/`variables`/`metaData`, plus `contacts[]`) so it can be fed straight back in:

```python
unsent = ex.get(f"/v2/throttle-schedule/{tid}/unsent")["data"]
if unsent.get("recipients"):
    ex.post(f"/v2/throttle-schedule/{new_tid}/recipients", {"recipients": unsent["recipients"]})
```

There is no per-recipient failure reason here. Cross-reference
`esendex-track-delivery` if the cause is needed before retrying, and scrub against
the opt-out list (`esendex-manage-contacts`) first: someone may have opted out
mid-campaign, and re-sending to them would be a breach.

## List query parameters

| Parameter | Notes |
| --- | --- |
| `FromStartDate` / `ToStartDate` | `YYYY-MM-DD` |
| `FromCreatedDate` / `ToCreatedDate` | `YYYY-MM-DD` |
| `Status` | `Active` \| `Paused` \| `Cancelled` \| `Failed` \| `Completed` \| `PartiallyCompleted` |
| `Msisdns` / `msisdn` | Recipient number filter. Both spellings are listed; confirm which one filters results with a quick test |
| `PageSize` | 1–1000, default 1 |
| `PageNumber` | 1+, default 1 - note `PageNumber`, not `PageNo` as templates use |
| `OrderDir` | `Asc` \| `Desc`, default descending |
| `Channel`, `OrderBy` | Further filters and sorting |

## Read response fields

`data.throttleScheduleInformation`: `id`, `createdAt`, `accountReference`,
`tenantCode`, `userId`, `startDate`, `timeSlotStart`, `timeSlotEnd`, `endDate`,
`rateOfSend`, `status`.
`data.dispatch`: as the delayed schedule.
`data.recipients[]`: `id`, `msisdn`, `orderNumber`, `variables`, `metaData`.
`data.contacts[]`: `id`, `contactId`, `orderNumber`.

`throttleScheduleId` is the field name on write responses but plain `id` inside
`throttleScheduleInformation` on reads. Same pattern for `scheduleId` on delayed
schedules.

`ex.paginate` assumes the paged `{pageIndex, pageSize, count, items[]}` wrapper. On a
bare `get`, check `data.items` exists before reading it.

## Cloning a campaign

There is no duplicate endpoint. GET the schedule, lift `dispatch` and the recipient
data, and POST it as a new schedule with fresh dates.

## Field names, collected

| Field | Where |
| --- | --- |
| `timeSlotStart` | Throttle `throttleScheduleInformation` |
| `rateOfSend` | Throttle `throttleScheduleInformation` |
| `daysOfWeek` | Throttle `throttleScheduleInformation` |
| `contacts[].contactId` | Throttle create and add-recipients |
| `recipients[]` with `msisdn`, `variables`, `metaData` | Every schedule body, including add-recipients |
| Top-level `contacts[]` / `groups[]` | Delayed create |
| `/v2/throttle-schedule/{id}/recipients` | Add-recipients path |

If a field appears to have no effect, check its spelling and casing first.
