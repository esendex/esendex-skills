# Request and response conventions

The long form of the shared mechanics summarised in `SKILL.md`. Read this when a
call is failing for no obvious reason, or when a field that was set appears to
have no effect.

It draws on the Esendex developer docs at https://developer.esendex.co.uk. Where a point matters, check it against
live behaviour and tell the user what was tested.

## Headers

| Header | When | Notes |
| --- | --- | --- |
| `X-Api-Key` | Always | Exact spelling, including the `X-` prefix |
| `X-External-Source: AI-Skill` | Always | Attribution for traffic sent through these skills. Not an Esendex docs requirement; a fixed value the skills always send. The bundled client adds it |
| `AccountReference` | Reads, and harmless on writes | `EXUK0000000` - `EX` + territory + 7 digits |
| `Content-Type: application/json` | Any request with a body | Omitting it on a POST returns a 400 |
| `Accept: application/json` | Optional | The API returns JSON regardless |

Sending `Api-Key` without the `X-` prefix gives a 401 whose body says the route
"was unauthenticated", which reads as a bad or expired key and can lead to a
valid key being regenerated unnecessarily. Check the header name before the key
value whenever a 401 appears on a first integration.

Credentials cannot be passed as query parameters, in a body field, or via HTTP
Basic. `-u user:pass` belongs to the legacy XML API; see the v2 note in
`SKILL.md` and `references/gotchas.md`.

## Account reference placement

The account reference is a header on reads and a body field on most writes:

```
GET  /v2/messages          AccountReference: EXUK0000000   (header)
POST /v2/messages          {"accountReference": "EXUK0000000", ...}   (body)
```

The bundled client sends the header on every request regardless of method;
`accountReference` must be added to write bodies by the caller. Sending both is
harmless; sending neither on a write is a 400 that names the missing field.

Accounts in different territories are separate account references, and a key issued
in one territory does not reach another. Multi-factor authentication in the portal
is also per territory.

## Error body shapes

Error responses come in three shapes. `EsendexError` in
`scripts/esendex_client.py` parses all three, so callers get a readable message
instead of a `KeyError` on whichever shape they did not expect.

Shape A - the common one, used by most endpoints for 400/401/404/409:

```json
{
  "errors": [
    {
      "errorCode": "message_not_found",
      "errorMessage": "A message with the given id does not exist",
      "metadata": {"additionalProp1": "string"}
    }
  ]
}
```

`metadata` is present in the schema on several pages but is often absent or
empty in responses, so do not depend on it.

Shape B - a nested envelope returned by 401s on some endpoints:

```json
{
  "title": "...",
  "status": 401,
  "internalErrors": [{"metadata": {"<code>": "<message>"}}]
}
```

The code and message live as key/value pairs inside
`internalErrors[].metadata`, not in named fields. `EsendexError` flattens those
pairs into its `codes` and `messages` lists.

Shape C - flat, returned by `/v2/balance-alerts` for 400:

```json
{"status": 400, "errorCode": null, "errorMessage": "String", "metadata": {}}
```

`errorCode` can be `null`, so treat the code as optional and always fall back to
`errorMessage`.

Because there are three shapes, never branch on `body["errors"][0]["errorCode"]`
directly. Catch `EsendexError` and read `.status`, `.codes` and `.messages`.

## Status codes

Endpoints can return status codes beyond those listed for them. The common ones:

| Status | Typical code | Meaning |
| --- | --- | --- |
| 200 | - | Succeeded. Not necessarily a success for every row - see below |
| 201 | - | Created |
| 204 | - | Succeeded with no body, on deletes. The client returns `None` |
| 400 | often absent | Missing or invalid field. Rarely carries a specific code, so read `errorMessage` |
| 401 | `unauthenticatedError` | Usually the wrong header name, not the wrong key |
| 403 | - | Not an admin, or an invalid parent/child account relationship. Returned on wallet delegation |
| 404 | `message_not_found`, `contact_not_found`, `group_not_found`, `template_not_found`, `account` | Also returned for a *malformed* id, not only a missing one |
| 409 | `contact_already_exists`, `group_already_exists` | Duplicate. Group names must be unique per account |
| 429 | - | Rate limited. Wait 5 seconds. No `Retry-After` header |
| 5xx | - | Retry with backoff. The client retries twice |

The 404-on-malformed-id behaviour matters while debugging. Passing a truncated GUID,
an integer where a GUID is expected, or a reference with a stray space returns the
same "does not exist" body as an absent record. A 404 is therefore not
proof the resource is gone: validate the id shape before concluding anything about
the data.

## 2xx responses with per-item failures

Two operations return a successful status with per-item failures inside the body.
Checking only the status code can miss rejected items.

Bulk contact create and bulk create-or-update return 200 with a per-row outcome:

```json
{"data": {"contacts": [{"result": "FAILED", "reasons": ["..."], "phoneNumber": "+447..."}]}}
```

Iterate the rows and count the failures. A 200 here can mean every single row was
rejected.

Delayed (scheduled) message creation returns 201 with a validation block:

```json
{"data": {"validationResult": {"isValid": false, "errors": ["..."]}}}
```

`isValid: false` inside a 201 means nothing is scheduled. Assert on
`validationResult.isValid`, not on the status.

## Pagination

Every list endpoint defaults to `pageSize=1`.

`GET /v2/messages` with no parameters returns one message and a `totalCount` that
is easily overlooked. The result looks like an account that has sent one message,
or a filter that matched one row, which can lead to the conclusion that the account
is empty, the filter is wrong, or the data was never written, and send debugging in
the wrong direction.

Always set the page size explicitly, or use `ex.paginate()`, which sets 1000.

The parameter names vary by endpoint:

| Concept | Spellings seen |
| --- | --- |
| Page size | `PageSize`, `pageSize` |
| Page number | `PageNo`, `pageNo`, `PageNumber` (throttle schedules) |

Instead of guessing per endpoint, the bundled client sends every spelling together
on every list call. Unknown query parameters are ignored, so this is harmless and
the endpoint picks up whichever spelling it expects.

List responses wrap results under `data`:

```json
{"data": {"messages": [...], "totalCount": 412, "currentPage": 1, "totalPages": 5}}
```

The array name varies by endpoint (`messages`, `contacts`, `groups`, `templates`,
`optOuts`, `requests`, `items`). `ex.paginate(path, key="messages")` takes the name;
if it is omitted, the client uses the first list-valued key it finds under `data`.
Stopping condition: an empty array, or `currentPage >= totalPages`.

## Casing

Casing differs by layer, and it is the first item to check when a field that
was set has no effect. The API ignores unknown fields, so a mis-cased field has no
effect and returns no error.

| Layer | Convention | Examples |
| --- | --- | --- |
| Request bodies | camelCase | `accountReference`, `messageType`, `templateType` |
| Query parameters | PascalCase or camelCase; send both | `PageSize`, `Status`, `AccountReference` |
| Webhook payloads pushed to the integration | PascalCase | `RequestId`, `Msisdn`, `Status` |
| Response fields | camelCase, but not always the request name | templates take `templateType` and return `type` |

Two cases to watch:

- `templateType` going in, `type` coming out. Round-tripping a template object
  straight back into an update call drops the type.
- `subaccountReference` (lower-case `a`) on wallet delegation. A mis-cased
  `subAccountReference` is ignored. See `references/balance-wallet.md`.

Because a wrong key is ignored, not rejected, verify writes by reading the
resource back, especially the first time an endpoint is called.

## E.164 formatting and the missing plus

Recipient numbers must be `+{country dial code}{number}` with no spaces or
punctuation, and with the national trunk `0` stripped where the country uses one.

| Input | Country | Dial code | E.164 |
| --- | --- | --- | --- |
| 07700900123 | UK | 44 | +447700900123 |
| 0491570156 | Australia | 61 | +61491570156 |
| 0123456789 | France | 33 | +33123456789 |
| 15223433333 | Germany | 49 | +4915223433333 |
| 3471234857 | Italy | 39 | +393471234857 |
| 912345678 | Spain | 34 | +34912345678 |
| 5417543010 | USA | 1 | +15417543010 |

Do not apply a blanket strip-the-leading-zero rule: whether there is a trunk `0`
to remove depends on the country and the input, and the Germany row's input has
none. `to_e164()` handles `+`, `00` and national forms.

Direction matters. Send requests use the leading `+` (`+447700900032`). Webhook
payloads come back without it (`447700900540`). Comparing a webhook `Msisdn`
against a stored recipient without normalising makes every lookup miss. Normalise
on ingest, in one place.

Email-to-SMS is the exception: its examples accept UK national format
(`07700900440`), unlike the REST API.

## Rate limiting

A 429 means the default per-endpoint rate limit was hit. The documented remedy is
to wait 5 seconds and retry. There is no `Retry-After` header to read, so the
integration should react to 429s instead of trying to compute a safe send rate in
advance. The limit is adjustable by arrangement with Esendex.

The bundled client sleeps 5 seconds and retries on 429, making up to
`max_retries` attempts in total (default 3). That suits occasional bursts. For bulk volume, use a throttle schedule
(`esendex-send-message`), the platform's mechanism for spreading a large batch over
time; a retry loop around `/v2/messages` spends most of its time waiting and
delivers unevenly.

SMPP has separate and much more specific limits: 5 `submit_sm` per second per
session, window size 1, with a different failure mode (`ESME_RTHROTTLED`, where the
submission is dropped, not queued). See `esendex-connect-smpp`.
