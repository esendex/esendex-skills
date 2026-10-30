---
name: "esendex-send-message"
description: "Send SMS through Esendex (Commify) v2: immediately via POST /v2/messages, at a future time via delayed schedules, or at a controlled rate via throttle schedules, with reusable templates, per-recipient personalisation, and GSM/Unicode part counting so cost is known before anything goes out. Use this skill whenever the user wants to text, message, notify or blast customers or a list, schedule a send for later, spread a large campaign out over hours or days, pause or cancel one already in flight, work out what a send will cost, or debug a rejected or failed send, including asks like \"text my customers\" or \"schedule this for Monday\" that never name the API."
---

## Terms of Service

Use of the Esendex (Commify) platform and APIs described below is governed by the Commify **[Terms of Service](https://enhancedsupport.esendex.co.uk/terms-of-service/)**, together with the [Acceptable Use Policy](https://enhancedsupport.esendex.co.uk/acceptable-use-policy/), [Data Processing Agreement](https://enhancedsupport.esendex.co.uk/data-processing-agreement/) and [Service Level Agreement](https://enhancedsupport.esendex.co.uk/service-level-agreement/). The contracting entity and governing law depend on where the customer is registered - Esendex UK&I contracts with Commify UK Limited under the laws of England and Wales.

Most relevant to this skill: Tariffs are incurred at the point of submission irrespective of delivery; the customer is responsible for complying with destination-country timing and quiet-hours rules and with the Acceptable Use Policy; Sender IDs must be registered where the destination requires it. A send cannot be recalled.

The terms are updated from time to time and the version available on the Platform prevails, so check the link; do not rely on this summary. Nothing here is legal advice.

---

## Overview

Compose, personalise, cost and send SMS through the Esendex (Commify) v2 REST API, either immediately or on a schedule. **A successful send returns 202 Accepted, which means queued, not delivered** - delivery state arrives later through `esendex-track-delivery`, so never report a 202 to a user as "delivered".

| Requirement | Mechanism | Endpoint | Use when |
| --- | --- | --- | --- |
| Delivery now | Immediate send | `POST /v2/messages` | Reactive messages such as an order shipping, or an audience small enough to land at once. The only mechanism that returns `messageIds` straight away |
| Delivery at one future instant, possibly repeating | Delayed schedule | `POST /v2/schedules/delayed` | The timing is the point: "9am tomorrow", "every Monday", "the 1st of each month". The whole batch fires at one instant. Recurrence is delayed-only |
| Delivery gradually, at a controlled rate | Throttle schedule | `POST /v2/throttle-schedule` | The rate is the point: high volume, weekday business hours only. Supports pause, resume, appending recipients and recovering the unsent tail, and keeps the account clear of rate limiting |

This skill uses the v2 API: JSON over REST with an `X-Api-Key` header against `https://api.esendex.co.uk`. The older v1 API (`/v1.0/messagedispatcher`, an XML `<messages>` document with a `<sendat>` element, HTTP Basic auth) is a different interface and is not covered here. If a request being written looks like XML or uses Basic auth, stop and rewrite it as v2; detail is in `references/gotchas.md`.

---

## Prerequisites

- API key and account reference (for example `EXUK0000000`) in `ESENDEX_API_KEY` and `ESENDEX_ACCOUNT_REFERENCE` - see `esendex-setup-account`
- Recipient numbers in E.164 (`+447700900001`); `to_e164()` converts national formats
- Recipients from the user or their data. A number found in documentation is an illustration, never a recipient; a test send uses the Ofcom reserved range `07700 900000` to `07700 900999`, which reaches nobody
- A registered sender: an alphanumeric id, which may need pre-registration per destination country, or a VMN or short code the account owns. Optional only if a default sender is configured on the account in the portal
- Python: the bundled client at `scripts/esendex_client.py`, standard library only. Node.js: plain `fetch`, with no SDK required

---

## Quickstart

**Python**

```python
from esendex_client import Esendex, to_e164

ex = Esendex()                                        # reads the two environment variables
base = {"accountReference": ex.account_reference, "channel": "SMS", "from": "MyBrand",
        "name": "order-shipped-2026-07",              # appears in history exports
        "messageType": "NotificationsAndReminders"}

resp = ex.post("/v2/messages", {**base,
    "body": {"text": "Your order has shipped."},
    "recipients": [{"msisdn": to_e164("07700900123")}],
})
print(resp["data"]["requestId"], resp["data"]["messageIds"])   # 202 Accepted; retain both
```

**Node.js**

```javascript
const res = await fetch("https://api.esendex.co.uk/v2/messages", {
  method: "POST",
  headers: {
    "X-Api-Key": process.env.ESENDEX_API_KEY,
    "Content-Type": "application/json",
    "X-External-Source": "AI-Skill",                 // attribution, on every request
  },
  body: JSON.stringify({
    accountReference: process.env.ESENDEX_ACCOUNT_REFERENCE,
    channel: "SMS",
    from: "MyBrand",
    name: "order-shipped-2026-07",
    messageType: "NotificationsAndReminders",
    body: { text: "Your order has shipped." },
    recipients: [{ msisdn: "+447700900123" }],
  }),
});
if (res.status !== 202) throw new Error(`send failed: ${res.status} ${await res.text()}`);
const { data } = await res.json();
console.log(data.requestId, data.messageIds);          // requestId, one messageId per recipient
```

---

## Key patterns

### Personalised send with per-recipient variables

```python
recipients = [
    {"msisdn": "+447700900001", "variables": {"firstName": "Alex", "orderId": "A123", "deliveryDate": "Friday"}},
    {"msisdn": "+447700900002", "variables": {"firstName": "Sam", "orderId": "A124", "deliveryDate": "Monday"}},
]
ex.post("/v2/messages", {**base,
    "body": {"text": "Hi [firstName], order [orderId] arrives [deliveryDate]."},
    "recipients": recipients,
})
```

Placeholders are square-bracketed names matched to keys in each recipient's `variables` object. Exactly one of `recipients` (1–50,000) or `addressBook` is required; sending by `addressBook.contacts[].id` instead turns each contact's stored custom fields into variables automatically, which removes the need for a variables map - see `esendex-manage-contacts`.

### Template send

```python
created = ex.post("/v2/templates", {
    "name": "Order shipped", "templateType": "Text", "messageType": "NotificationsAndReminders",
    "content": "Hi [firstName], order [orderId] has shipped and arrives [deliveryDate].",
    "channelSettings": {"sms": {"characterSet": "Auto"}},
})
ex.post("/v2/messages", {**base, "body": {"templateId": created["data"]["id"]},
                         "recipients": recipients})
```

`body` takes `text` or `templateId`, never both. Create returns 201 with `data.id`; update, delete, lock, unlock and tag changes all return 204 with no body, so do not parse one. Templates are most useful where wording must stay consistent across a team, where content has been through compliance review and should not drift, and on accounts whose users may only send predefined templates; list them with `ex.paginate("/v2/templates", key="templates")`, since `PageSize` defaults to 1.

### Cost check before sending

```python
from esendex_client import sms_part_count

sms_part_count("Your order has shipped.")    # -> 1, GSM
sms_part_count("Your order has shipped 🚚")   # -> 1, but Unicode-encoded, 70-char cap now
parts = sms_part_count(text)                 # "a" * 200 -> 2
print(f"{parts} x {len(recipients)} = {parts * len(recipients)} billable messages")
```

`characterSet` accepts `Auto`, `GSM` or `Unicode`; GSM fits ~160 characters in a single part and ~153 per part concatenated, Unicode ~70 and ~67. This is a pre-flight estimate against documented capacities, not a billing guarantee: the billed figure is `messagePartCount` on the message record (`esendex-track-delivery`), and balance and per-message pricing are `esendex-setup-account`. Quote anything large in billable messages, not characters, since that is the number the user acts on.

### Delayed schedule with UTC conversion

```python
from datetime import datetime
from zoneinfo import ZoneInfo

# UTC-only, no timezone field: 9am London on 3 August is BST, so sendTime is 08:00:00.000Z
local = datetime(2026, 8, 3, 9, 0, tzinfo=ZoneInfo("Europe/London"))
send_time = local.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%S.000Z")

resp = ex.post("/v2/schedules/delayed", {
    "scheduleInformation": {"sendTime": send_time, "frequency": "Weekly", "repeatTimes": 4},
    "dispatch": {"channel": "SMS", "from": "MyBrand", "name": "August reminder",
                 "messageType": "NotificationsAndReminders",
                 "body": {"text": "Hi [firstName], your appointment is tomorrow."}},
    "recipients": [{"msisdn": "+447700900001", "variables": {"firstName": "Alex"}}],
})
schedule_id = resp["data"]["scheduleId"]
```

`frequency` accepts `Daily`, `Weekly`, `Monthly`, `Annually`, `Weekdays` and `Weekends`, and always needs an explicit `repeatTimes`; omit both for a one-off. A 201 does not mean valid, so check `data.validationResult.isValid` and its `errors[]` (`propertyName`, `errorMessage`, `attemptedValue`). Cancel with `DELETE /v2/schedules/delayed/{scheduleId}`; a `requestId` or `messageId` will fail.

### Throttle schedule

```python
resp = ex.post("/v2/throttle-schedule", {
    "throttleScheduleInformation": {
        # 08:00-17:00 UTC is 09:00-18:00 BST. Convert from the user's local window.
        "startDate": "2026-08-03", "timeSlotStart": "08:00:00", "timeSlotEnd": "17:00:00",
        "rateOfSend": 2000,        # or endDate + timeSlotEnd, and the platform picks the rate
        "daysOfWeek": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
    },
    "dispatch": {"channel": "SMS", "from": "MyBrand", "name": "Renewal campaign",
                 "messageType": "MarketingAndResearch",
                 "body": {"text": "Hi [firstName], your policy renews soon."}},
    "recipients": [{"msisdn": "+447700900001", "variables": {"firstName": "Alex"}}],
})
tid = resp["data"]["throttleScheduleId"]
print(resp["data"]["estimatedEndDateTime"], resp["data"]["numberOfRecipients"])
```

`rateOfSend` is messages per hour. Supply either it or `endDate` plus `timeSlotEnd`, in which case the platform calculates the optimal rate and returns `estimatedRateOfSend`: "one of end date of the throttle or the rate of send must be provided". `timeSlotStart` / `timeSlotEnd` and `daysOfWeek` confine sending to staffed business hours, which stops messages landing at 3am and keeps inbound replies answerable. All three are UTC, so convert from the user's local window before setting them.

A throttle create returns no `validationResult`, unlike a delayed create, so verify it by reading back `numberOfRecipients` and the echoed rate before reporting success.

### Pause, resume and add recipients

```python
ex.post(f"/v2/throttle-schedule/{tid}/pause")     # 204, no body
ex.post(f"/v2/throttle-schedule/{tid}/resume")    # 200, recalculated ETA and rate
ex.post(f"/v2/throttle-schedule/{tid}/recipients", {                  # note the slash
    "recipients": [{"msisdn": "+447700900002", "variables": {"firstName": "Sam"}}],
})
ex.delete(f"/v2/throttle-schedule/{tid}")         # 204, cancel
```

States run `Active` → `Paused` → `Active` and `Active`/`Paused` → `Cancelled`; `Completed`, `PartiallyCompleted` and `Failed` are terminal. Only `Paused` schedules resume, only `Active` or `Paused` schedules cancel, and recipients can be added only while `Active` or `Paused`. Resuming re-spreads the remainder from now and adding recipients pushes `estimatedEndDateTime` out, so check the status before promising to stop a campaign.

### Recover unsent recipients

```python
unsent = ex.get(f"/v2/throttle-schedule/{tid}/unsent")["data"]
if unsent.get("recipients"):
    ex.post(f"/v2/throttle-schedule/{new_tid}/recipients", {"recipients": unsent["recipients"]})
```

`GET /v2/throttle-schedule/{id}/unsent` is populated when a schedule ends `PartiallyCompleted`, `Cancelled` or `Failed`, and is shaped like a request body so it feeds straight back in. It carries no per-recipient failure reason: cross-reference `esendex-track-delivery` for the cause, and scrub opt-outs (`esendex-manage-contacts`) before resending, since someone may have opted out mid-campaign. There is no clone endpoint - GET the schedule, lift `dispatch` and the recipient data, and POST it as a new schedule with fresh dates.

---

## Common errors

| Code | Meaning | Fix |
| --- | --- | --- |
| 400 | Missing or invalid required property | Usually both `text` and `templateId`, neither `recipients` nor `addressBook`, or a missing `from` with no account default |
| 401 `unauthenticatedError` | Key wrong, or in the wrong header | Send the key in the `X-Api-Key` header |
| 404 `template_not_found` / `update_schedule_not_found` | Unknown or malformed id | Check the id, and that a schedule has not already fired or been cancelled |
| 429 | Rate limited, with no `Retry-After` | Wait 5 seconds; the bundled client retries automatically |
| `senderIdInvalid` | Sender not registered or not owned | Check the sender before the recipient: register the alphanumeric id, or use a purchased VMN or short code |
| `MsisdnInvalid` | Not a valid destination number | Normalise with `to_e164()` before submitting |
| `OptedOut` | Recipient has opted out | Do not retry; scrub the list (`esendex-manage-contacts`) |
| `WithinQuietHours` | Blocked by local quiet-hours rules for this `messageType` | Reschedule outside quiet hours; do not relabel the traffic |
| `OutsideBusinessHours` | Blocked by a business-hours restriction | Reschedule, or set throttle `timeSlotStart` / `timeSlotEnd` |
| `SendingLimitExceeded` | Account or campaign limit reached | Spread the send over a throttle schedule; check limits in `esendex-setup-account` |
| `MessagePartCountExceeded` | Too many parts for the message | Shorten the text, or remove the non-GSM character forcing Unicode |
| `LandlineNotAllowed` | Destination is a landline | Remove it from the audience |
| `DestinationNotAllowed` | Destination country not enabled on the account | Confirm destination permissions with support |

The `reason` values are per-recipient and do not appear in the send response: a 202 followed by individual failures is normal. Read them from each message record, and see `esendex-track-delivery` for the full list plus polling and webhook mechanics.

---

## Gotchas

Every row is covered in more detail in `references/gotchas.md`.

| Behaviour | What to do |
| --- | --- |
| `addressBook.contacts` takes at most 10,000 contact ids per request | Keep contact-id batches at or below 10,000 and page through anything larger |
| Placeholders are square-bracketed names matched to each recipient's `variables` keys | Use `[name]` with a matching `variables` key, and prove it with one live test before a large personalised run |
| `body` accepts `text` or `templateId`, never both | Supplying both is a 400, as is supplying neither `recipients` nor `addressBook` |
| Alphanumeric senders cannot receive replies | Never send "reply STOP" copy from one; use a VMN, a short code, a link or a phone number |
| One emoji or non-Latin character flips the whole message to Unicode, cutting capacity from 160 to 70 | Cost the send first and name the character that raised the part count, since it is usually removable |
| `[shorten:...]` is unavailable on trial accounts | A shortener send failing on a new account needs an upgrade, not a retry |
| Scheduling is UTC-only, with no timezone field anywhere | Convert from the intended timezone and state the conversion: 9am on 3 August in London is 08:00Z |
| Omitting `repeatTimes` with `frequency` set repeats the schedule indefinitely | Always set an explicit count and state it; `repeatTimes` without `frequency` errors |
| `Weekdays` and `Weekends` are separate `frequency` values | Send one of them alone, never combined, and test with a short-lived schedule |
| Delayed `PATCH` reaches only `sendTime` and `dispatch.name`, and must land 5 minutes before the send | Inside that window, say so and point at the portal or support instead of retrying |
| A 201 on a delayed schedule create does not mean the schedule is valid | Check `data.validationResult.isValid` and its `errors[]` before reporting success. Throttle creates carry no `validationResult`; verify those by reading back `numberOfRecipients` and the echoed `rateOfSend` |
| Templates return `type` where the request sends `templateType`, and `channelSettings` comes back as an array whose `settings` is a JSON-encoded string | Rebuild the write shape by hand; a GET response cannot be fed into a `PUT` |
| The template tags endpoint takes tag GUIDs, not names | Send `{"tagIds": ["<guid>"]}`; success is 204 with no body |
| Tags are managed in the portal | Ask the user for the GUIDs; do not offer to create or list tags |
| Field names are case-sensitive | Use `timeSlotStart`, `rateOfSend`, `daysOfWeek`, `contacts[].contactId`; if a field seems to have no effect, check its spelling and casing first |

---

## CANNOT

- **Cannot recall a sent message.** Once the platform has accepted a submission there is no undo; only a schedule that has not yet fired can be cancelled.
- **Cannot be recurring and throttled at once.** `frequency` exists only on delayed schedules, so a repeating drip-feed means recreating the throttle schedule each cycle.
- **Cannot start a throttle schedule at a precise minute.** `startDate` is a date and `timeSlotStart` a time, so sending begins somewhere within the slot.
- **Cannot send in each recipient's local timezone.** The platform is UTC-only: segment by region into separate schedules, or state plainly that one schedule means one wall-clock instant worldwide.
- **Cannot change message text once a schedule exists.** Cancel and recreate; the same applies to recipients, sender and frequency.
- **Cannot edit a delayed schedule within 5 minutes of its send time.** The update fails or does not take effect, so direct the user to the portal or support.
- **Cannot edit a throttle schedule once every message has been accepted.** "Stop this campaign" works only before it finishes; if the status is `Completed`, say so instead of issuing a cancel.
- **Cannot reply to an alphanumeric sender.** STOP-style copy is unfulfillable from one, so the opt-out route must be a link, a phone number, a VMN or a short code.

---

## Before a bulk send

A send cannot be unsent and a schedule fires without asking anyone again, so run this before anything going to more than a handful of real recipients, or that the user has not explicitly confirmed in this conversation.

1. Echo back the audience size, the sender, and a fully rendered sample with real variable values substituted: a wrong `from` or an unintended 50,000-recipient audience is expensive and irreversible.
2. Quote the cost as billable messages (parts × recipients), and say whether an emoji or non-Latin character is what pushed the part count up, since that is usually removable.
3. Scrub opt-outs (`esendex-manage-contacts`): sending to someone who replied STOP is a compliance breach.
4. Set `messageType` accurately, because it drives quiet-hours and local regulatory rules; mislabelling marketing as `NotificationsAndReminders` to get past a block is a compliance problem, and the answer to a quiet-hours block is a different send time.
5. Check the sender can carry the opt-out route the copy promises: alphanumeric senders cannot receive replies, so "reply STOP" needs a VMN, a short code, or rewording.
6. For a schedule, state the UTC time converted to and the repeat count set.
7. Send one test to yourself first, especially with variables, a template or a shortened URL.
8. Set `name` and `metaData` so the campaign can be found and reconciled later.
9. For anything large, prefer a throttle schedule to one enormous request: it spreads network and inbox load, keeps the account clear of rate limits, and gives pause, resume and unsent recovery if something turns out to be wrong.

---

## Next steps

- **Credentials, account references, E.164, rate limits, balance and per-message cost:** `esendex-setup-account`
- **Did it arrive, why it failed, delivery webhooks, click tracking on shortened URLs:** `esendex-track-delivery`
- **Contacts, custom fields, groups, opt-out scrubbing:** `esendex-manage-contacts`
- **The separate SMPP interface, for an existing SMPP client:** `esendex-connect-smpp`
- **Full `POST /v2/messages` parameter tables, `validity`, `metaData`, the `messageType` enum, other cURL-sample fields:** `references/sending.md`
- **All nine template endpoints, locking, copying to sub-accounts, deletion consequences:** `references/templates.md`
- **All fourteen schedule endpoints, list filters, the validation-result schema, response field names:** `references/scheduling.md`
- **Every gotcha above in full, with what to do:** `references/gotchas.md`
- **The full API reference:** the Esendex developer docs at https://developer.esendex.co.uk

