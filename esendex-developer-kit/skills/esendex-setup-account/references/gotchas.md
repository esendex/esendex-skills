# Gotchas in full

One section per row of the Gotchas table in `SKILL.md`, plus the v2-only guard. Each describes
the behaviour, how it shows up, and what to do. Where a point matters to the user's outcome, test it
against the live API and tell the user what was tested.

The points here draw on the Esendex developer docs at https://developer.esendex.co.uk.

## `Api-Key` versus `X-Api-Key`

The header is `X-Api-Key`, on every request. The bundled client sends it.

A bare `Api-Key` header returns a 401 whose body reads
`Request for authenticated route '/v2/balance' was unauthenticated`. That reads like a bad or
expired key, so a common response is to regenerate a valid key, which then returns the same 401.

What to do: on a 401 from a new integration, check the header name before touching the key
value. Credentials cannot be passed as a query parameter, in a body field, or via HTTP Basic;
`-u user:pass` belongs to the legacy XML API (see the last section).

## `pageSize` defaults to 1

Every list endpoint defaults to `pageSize=1`.

A bare `GET /v2/messages` returns one message and a `totalCount` that is easily overlooked. The
result looks like an account that has sent one message, or a filter that matched one row, which
can lead to the conclusion that the account is empty, the filter is wrong, or the data was never
written, and send debugging in the wrong direction.

The parameter names also vary by endpoint. Page size appears as `PageSize` and
`pageSize`; page number as `PageNo`, `pageNo` and `PageNumber` (the last on throttle
schedules).

What to do: always set the page size explicitly, or use `ex.paginate()`, which sets 1000 and
sends every spelling together on every call. Unknown query parameters are ignored, not
rejected, so sending all the variants is harmless and removes the guesswork. The full
pagination detail, including the `data` wrapper and the stopping condition, is in
`references/conventions.md`.

## Three error body shapes

Error responses come in three envelopes, depending on the endpoint and status.

Shape A, used by most endpoints for 400/401/404/409, is a flat `{"errors": [{"errorCode",
"errorMessage", "metadata"}]}`. Shape B is a nested envelope returned by 401s on some
endpoints - `{"title", "status", "internalErrors": [{"metadata"}]}` - where the code and
message live as key/value pairs inside `internalErrors[].metadata` instead of in named fields.
Shape C, returned by `/v2/balance-alerts` for 400, is flat and unwrapped: `{"status",
"errorCode", "errorMessage", "metadata"}`, where `errorCode` can be `null`.

A client that assumes one shape raises a `KeyError` on the others.

What to do: never branch on `body["errors"][0]["errorCode"]`. Catch `EsendexError`, which
parses all three and exposes `.status`, `.codes` and `.messages`, and always fall back to
`errorMessage` because the code is often absent or null. The complete catalogue with sample
bodies is in `references/conventions.md`.

## 2xx responses with per-item failures

Two operations return a successful status code with per-item failures inside the body, so
checking only the status can miss rejected items.

Bulk contact create and bulk create-or-update return 200 with a per-row outcome under
`data.contacts`, each row carrying `result`, `reasons` and `phoneNumber`. A 200 can be
returned even when every row was rejected. Delayed (scheduled) message creation
returns 201 with `data.validationResult.isValid`; `false` means nothing was scheduled.

What to do: assert on the per-row `result` and on `validationResult.isValid`, not on the HTTP
status. Count the failed rows and report them.

## Casing by layer

Casing differs by layer. The API ignores unknown fields, so a mis-cased field has no effect
and returns no error.

Request bodies are camelCase (`accountReference`, `messageType`, `templateType`). Query
parameters appear in both PascalCase (`PageSize`, `Status`, `AccountReference`) and camelCase,
and sending both spellings covers either. Webhook payloads pushed to the integration are
PascalCase (`RequestId`, `Msisdn`, `Status`). Response fields are camelCase but not always the same name as the request
field that set them: templates take `templateType` and return `type`, so round-tripping a
template object straight back into an update call drops the type.

What to do: treat casing as the first thing to check when a field that was set has no effect,
and verify writes by reading the resource back, especially the first time an endpoint is
called. The layer-by-layer table is in `references/conventions.md`.

## Balance values are strings

`GET /v2/balance` returns `{"available": "2951.73346", "reserved": "0"}` - quoted strings, five
decimal places, at the top level with no `data` wrapper, unlike most of the API. The wallet
movement ledger returns `amount` as a number, so the two endpoints use different types for
monetary values.

Keep the string form for balances: it is an exact decimal.

What to do: parse with `Decimal`, not `float`, for any arithmetic on the value or comparison
against a threshold. Parsing the string directly avoids floating-point errors of the
`float("0.1") + float("0.2")` kind.

## No currency field

No endpoint in the API returns a currency field, including `/v2/balance` and the wallet
endpoints. The response does not indicate whether the number is GBP, EUR, USD or credits, and
the `EXUK` prefix on an account reference is a territory code, which does not identify the
account's currency.

What to do: never render a currency symbol inferred from the account reference or from the
user's locale. Label the value neutrally - "balance: 2951.73346" - or ask the user what the
account is denominated in. A guessed "£2951.73" on an account held in euros would misstate the
balance, while the bare number does not.

## Balance alerts are create-only

`POST /v2/balance-alerts` is the entire API surface. There is no GET, no PUT and no
DELETE: alerts cannot be listed, a threshold cannot be changed, and an alert cannot be
disabled or removed through the API. That makes them close to write-once.

`contactAddress` is a single string. `alertType` takes one value, `LOW_BALANCE`, which is
also the default; send it explicitly anyway. `threshold` is sent as an integer and echoes back
as a float (`1.0`).

What to do: create one alert deliberately, with a threshold derived from recent spend rather
than a round number, and avoid creating extras during testing, since the API cannot list or remove them
afterwards. For several recipients, use a distribution-list
address. Managing or removing alerts requires the portal. Full field table in
`references/balance-wallet.md`.

## `subaccountReference` versus `subAccountReference`

Wallet delegation takes `subaccountReference`, with a lower-case `a`. Unknown fields are
ignored, so a mis-cased `subAccountReference` may not be applied, and a 200 response is not
proof that funds moved.

Two other properties of the endpoint make verification important: a successful delegation
returns no response body, and a delegation cannot be reversed through the API.

What to do: send `subaccountReference`, and verify the delegation landed by reading
`GET /v2/balance` back for both the parent and the sub-account. If a delegation appears to have
done nothing, check the casing first. Full detail in `references/balance-wallet.md`.

## `api.esendex.com` versus `api.esendex.co.uk`

The base URL is `https://api.esendex.co.uk`. `api.esendex.com` is a common wrong guess.

What to do: use `https://api.esendex.co.uk`. HTTPS only; unencrypted HTTP is not supported.
Centralise the base URL so a stray `.com` host never ends up in a request; the bundled client
does this by default.

## The missing leading plus on webhook payloads

Whether a number carries the `+` depends on direction. Send requests take full E.164 with the
plus (`+447700900032`), and the docs are explicit that recipients must be
`+{country dial code}{number}` with no spaces or punctuation. Webhook payloads pushed back to
the integration return the number bare, without the plus (`447700900540`).

Each form is correct for its direction, so the integration needs to normalise between them.
Comparing a webhook `Msisdn` against a stored recipient without normalising makes every lookup
miss, and the symptom is inbound or delivery events that appear to belong to no known
recipient.

What to do: normalise on ingest, in one place, with `to_e164()`, and store one canonical form.
Note the related exception: email-to-SMS accepts UK national format (`07700900440`) in its
examples, unlike the REST API. The full conversion table, including France, Italy and Spain, is
in `references/conventions.md`.

## The legacy v1 XML API

Esendex previously offered an XML-based API, and AI models often reproduce it from memory when
asked for Esendex code. Anything resembling the following belongs to that legacy interface and
is not part of v2:

- Paths like `/v1.0/messagedispatcher`, `/v1.1/messagebatches`, or any `/v1.x/` path at all
- XML request or response bodies - `<messages>`, `<sendat>`, `<validity>`, `<FailureReason>`,
  `<reference>`
- HTTP Basic authentication with a username and password
- Numeric delivery failure codes such as 0, 4, 6, 7, 8, 12, 13, 16, 17, 101, 102, 199, 200, 999

The v2 API is JSON over REST, authenticated with the `X-Api-Key` header,
and its failure reasons are strings: `MsisdnInvalid`, `senderIdInvalid`, `OptedOut`,
`NetworkFailed` and the rest of the set catalogued in `esendex-track-delivery`.

Code written against the legacy interface can look correct, with well-formed XML and plausible
error handling, so it may pass review and only fail when it calls the API. A re-read will not
catch it; check each endpoint against the docs.

What to do: on reaching for a `<sendat>` element, a `messagedispatcher` path, a Basic auth
header or a numeric error code, stop and look the endpoint up in the Esendex developer docs at
https://developer.esendex.co.uk. Where the docs and memory disagree, follow the docs.
