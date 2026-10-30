# Reference: POST /v2/messages

Exhaustive parameter detail for an immediate send.

```
POST https://api.esendex.co.uk/v2/messages
```

Headers: `X-Api-Key`, `Content-Type: application/json`. Any other header name for the
key produces a 401.

Success is 202 Accepted, not 200.

## Required and conditional body parameters

| Parameter | Type | Req | Notes |
| --- | --- | --- | --- |
| `accountReference` | String | Required | e.g. `EXUK0000000`. Also accepted as the `AccountReference` header on other endpoints |
| `channel` | String | Required | `SMS` |
| `body` | Object | Required | Carries exactly one of `text` or `templateId` |
| `body.text` | String | Conditional | Required if no `templateId`. Variables in square brackets. `[shorten:https://...]` embeds a tracked short link - not available on Trial |
| `body.templateId` | GUID | Conditional | Required if no `text`. Mutually exclusive with `text` |
| `from` | String | Conditional | Required unless a default senderId is set on the account in the portal. Alphanumeric (may need pre-registration per destination country; cannot receive replies) or numeric (must be a VMN or short code you own) |
| `recipients` | Array | Conditional | One of `recipients` or `addressBook` is required. 1–50,000 objects |
| `recipients[].msisdn` | String | Required in each | E.164 |
| `recipients[].variables` | Object | Optional | `key: value` pairs substituted into `[key]` placeholders |
| `recipients[].metaData` | Object | Optional | Per-recipient key/value, returned on export |
| `addressBook` | Object | Conditional | Required if not using `recipients` |
| `addressBook.contacts` | Array | Conditional | Required when using `addressBook` |
| `addressBook.contacts[].id` | GUID | Conditional | Contact id. Contact custom fields become message variables automatically |
| `addressBook.groups[].id` | GUID | Optional | Group id. Verify with a small live send before relying on it |

### Contacts per request

`addressBook.contacts` takes at most 10,000 contact ids per request. Page through larger
audiences in batches of 10,000 or fewer.

## Optional body parameters

| Parameter | Type | Notes |
| --- | --- | --- |
| `name` | String | Friendly request label. Appears in message history export; enables later filtering by `requestName` |
| `characterSet` | String | `Auto` \| `GSM` \| `Unicode`. Default `Auto` |
| `validity` | Timestamp | Retry window. Must be more than 1 minute and less than 72 hours in the future. Default 72 hours. e.g. `2026-08-03T09:07:12.190Z` |
| `messageType` | String | Regulatory classification - see enum below |
| `metaData` | Object | Request-level key/value pairs, returned on export |

### messageType enum (send)

`MarketingAndResearch`, `NotificationsAndReminders`, `AuthenticationAndSecurity`,
`PaymentsAndCollections`, `InternalOperations`, `CustomerSupport`, `Conversational`.

Templates additionally accept `Unknown` and `BlueLight`, which are not in the send
enum.

This field is a compliance control: the platform uses it to apply local rules such as
quiet-hours restrictions on marketing traffic. Labelling a marketing send as
`NotificationsAndReminders` to get past a quiet-hours block is a compliance breach.

### characterSet capacity

| Set | Single part | Per part when concatenated |
| --- | --- | --- |
| GSM | ~160 | ~153 |
| Unicode (UCS-2) | ~70 | ~67 |

These are the figures `sms_part_count` implements.

`Auto` picks GSM unless the text contains a character that GSM cannot represent. The
GSM extended set - `^ { } \ [ ~ ] | €` - costs two characters each, so a message full
of square brackets is more expensive than its length suggests.

## Response

```json
{"data": {"requestId": "8dcad127-...", "messageIds": ["0929df71-..."]}}
```

`requestId` identifies the whole submission; `messageIds` has one entry per recipient.
Retain both: delivery lookup in `esendex-track-delivery` needs them.

## Error responses

| Status | Meaning |
| --- | --- |
| 400 | Missing or invalid required property. `{"errors":[{"errorCode","errorMessage"}]}`. Most often: both `text` and `templateId`, neither `recipients` nor `addressBook`, or a missing `from` with no account default |
| 401 | `unauthenticatedError` - wrong or missing `X-Api-Key` |

Per-recipient failures are not 4xx. A 202 followed by individual failures is normal;
the `reason` field on each message record explains each one. See
`esendex-track-delivery` for the reason list and how to poll for it.

## Other cURL-sample fields

The cURL sample in the API reference also shows `body.shortenUrlBrand`, and a
`body.attachment` object with `attachmentUrl`, `fileName` and `description`. This skill
does not cover them. Confirm availability for the account with Esendex before using
them, and do not offer MMS-style attachments on the basis of the sample alone.

## URL shortening detail

Embed `[shorten:https://example.com/orders/12345]` in `body.text`. The platform
replaces it with a `uk.endx.io/abcd123` link that is unique per recipient, which is
what makes per-recipient click tracking possible. Click data is read through the
URL-shortener endpoints covered by `esendex-track-delivery`.

Not available on Trial accounts; the account needs upgrading first. Write the marker
with no space after the colon.
