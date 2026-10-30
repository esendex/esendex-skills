---
name: "esendex-connect-smpp"
description: "Connect to Esendex (Commify) over SMPP v3.4 - bind types and PDUs, TLS/VPN requirements and IP allowlisting, TON/NPI settings for source and destination addresses, GSM vs UCS2 data coding, concatenated long messages via UDH, throughput limits and ESME_RTHROTTLED handling, delivery receipt format, and the full message state and error code tables. Use this skill whenever the user mentions SMPP, binds, submit_sm, deliver_sm, enquire_link, PDUs, an SMSC or SMS gateway connection, is integrating an existing SMPP client or platform with Esendex, or is decoding a DLR stat/err value such as UNDELIV or err:83."
---

## Terms of Service

Use of the Esendex (Commify) platform and APIs described below is governed by the Commify **[Terms of Service](https://enhancedsupport.esendex.co.uk/terms-of-service/)**, together with the [Acceptable Use Policy](https://enhancedsupport.esendex.co.uk/acceptable-use-policy/), [Data Processing Agreement](https://enhancedsupport.esendex.co.uk/data-processing-agreement/) and [Service Level Agreement](https://enhancedsupport.esendex.co.uk/service-level-agreement/). The contracting entity and governing law depend on where the customer is registered - Esendex UK&I contracts with Commify UK Limited under the laws of England and Wales.

Most relevant to this skill: The customer is responsible for its own systems, connectivity and security controls, must not share credentials between Authorised Users, and remains liable for all Tariffs incurred by traffic submitted on its account even where the account has been compromised.

The terms are updated from time to time and the version available on the Platform prevails, so check the link; do not rely on this summary. Nothing here is legal advice.

---

## Overview

Esendex supports SMPP v3.4 only ([spec](https://smpp.org/SMPP_v3_4_Issue1_2.pdf)), as a
separate interface from the REST API with its own credentials, limits and error codes. SMPP
suits an existing SMPP client or a platform that requires an SMPP interface, whereas a
greenfield integration is simpler over the REST API (`esendex-send-message`).

| Bind type | Direction |
| --- | --- |
| `BIND_TRANSMITTER` | Send only; receive DLRs on a separate bind |
| `BIND_RECEIVER` | Receive DLRs and inbound messages only |
| `BIND_TRANSCEIVER` | Both on one bind; usually the simplest configuration |

Abbreviations used below: PDU = protocol data unit, DLR = delivery report, MC/SMSC = message
centre, ESME = external short message entity, bind = the session.

---

## Prerequisites

Esendex provisions each SMPP connection for the individual customer.

- The host, port, system_id and password are not published. Esendex supplies the endpoint
  address, port, systemID and password once provisioning is complete.
- Esendex must be told whether the connection will be secured by TLS 1.2 or higher, or by a
  requested VPN. Unsecured connections are not accepted.
- The source IP addresses that will be connected from must be provided for allowlisting.
  Nothing connects until Technical Services confirms the allowlisting is in place.
- Regional registration requirements may add setup time.
- Esendex is ISO 27001 accredited and TLS 1.2 is the preferred transport.
- `esendex-setup-account` covers the account model, balance and sender configuration.

---

## Connection parameters

| Parameter | Value or source |
| --- | --- |
| Endpoint address | Supplied by Esendex |
| Port | Supplied by Esendex |
| `system_id` | Supplied by Esendex |
| `password` | Supplied by Esendex |
| Transport | TLS 1.2 or higher (recommended), or plain SMPP tunnelled through a requested VPN |
| Bind type | `BIND_TRANSMITTER`, `BIND_RECEIVER` or `BIND_TRANSCEIVER` |
| Supported PDUs | `BIND_TRANSMITTER`, `BIND_RECEIVER`, `BIND_TRANSCEIVER`, `UNBIND`, `ENQUIRE_LINK`, `SUBMIT_SM`, `DELIVER_SM` |
| Concurrent sessions | Multiple simultaneous binds per account, scaling as needed |
| Window size | 1 - wait for the response to each PDU before sending the next |
| `submit_sm` rate | 5 per second, per transmitting session |
| DLR rate | 10 per second, per receiving session; adjustable via the account manager |
| `enquire_link` cadence | At least once a minute, and at most every 15 seconds |

Design the client around 5 submit_sm per second per session. For higher volume, open
additional sessions and apply flow control, or use the REST API's throttle schedules
(`esendex-send-message`); a shorter retry interval does not raise the limit. If the server sees no traffic for a minute it sends its
own `ENQUIRE_LINK`; no response disconnects the session.

---

## Submitting a message

| Field | Value |
| --- | --- |
| Data coding (DCS) | `0` or `1` for GSM 03.38, `8` for Unicode (UCS2) |
| Destination address | International numbers only, `TON = 1`, `NPI = 1` |
| Registered delivery | `0` or `1` |
| Validity period | Relative or absolute; relative must follow the 24-hour clock format, otherwise the account default applies. Set it explicitly if expiry timing matters |

UCS2 carries the same cost tradeoff as the REST API: roughly half the characters per part.

| Source type | TON | NPI |
| --- | --- | --- |
| International | 1 | 1 |
| National | 2 | 1 |
| Alphanumeric | 5 | 1 or 0 |

Alphanumeric senders may use `0-9`, `A-Z`, `a-z` and `!"#$%&'*+-./:<=>?@_`. All SMS sender
types work over SMPP: standard, short code, long code and alphanumeric.

### Fields to leave at their defaults

`service_type`, `schedule_delivery_time`, `replace_if_present` and `default_msg_id` must stay
at their defaults, 0 for integers and null for strings. These fields are not supported, and
a populated value may not return a specific error, so confirm the client leaves them unset.

---

## Long messages

Set ESM class to 64 and use the 8-bit or 16-bit UDH mechanism. The `sar_msg_ref_num`,
`sar_total_segments`, `sar_segment_seqnum` and `message_payload` TLVs are not supported. All
parts must be submitted over the same bind. If the platform does not receive every part
within a reasonable length of time, it returns a delivery report of `UNDELIV` for each
submitted part and does not attempt delivery of the message. Submit the parts of a message
in quick succession.

---

## Delivery receipts

Delivery receipts arrive in the `short_message` field of a `deliver_sm` PDU, per Appendix B of
the SMPP 3.4 spec, and are near-real-time:

```
id:{id} sub:{sub} dlvrd:{dlvrd} submit date:{YYMMDDhhmm} done date:{YYMMDDhhmm} stat:{stat} err:{err}
```

| Field | Octets | Meaning |
| --- | --- | --- |
| `id` | variable | Message id |
| `sub` | 3 | Parts originally submitted (may be zero-padded) |
| `dlvrd` | 3 | Parts delivered (may be zero-padded) |
| `submit date` | 10 | `YYMMDDhhmm` |
| `done date` | 10 | `YYMMDDhhmm`, when the message reached its final state |
| `stat` | 7 | Final status - text may be abbreviated |
| `err` | 3 | Network/SMSC error code |
| `text` | 20 | Unused |

DLRs also carry the `receipted_message_id` and `message_state` TLVs, which are preferable to
parsing the receipt text wherever the client exposes them.

---

## Message states

| State | Type | Meaning |
| --- | --- | --- |
| `ENROUTE` / `EN_ROUTE` | Intermediate | Active in the message centre, in retry or dispatched to the network; the only state that can still change |
| `DELIVERED` | **Final** | Delivered to the handset |
| `EXPIRED` | **Final** | Validity/retry period elapsed without delivery |
| `UNDELIVERABLE` | **Final** | Permanent delivery error; no further attempts |

Standard SMPP 3.4 also defines `DELETED`, `ACCEPTED`, `UNKNOWN` and `REJECTED`, so handle
unexpected values gracefully instead of assuming a closed set.

`stat` is 7 octets and abbreviated on the wire, so expect `DELIVRD`, `UNDELIV`, `ENROUTE` and
`EXPIRED`, and match on the abbreviated forms.

---

## Error codes

Esendex uses 11 SMPP error codes, shown here in decimal:

| Code | Meaning | Retry |
| --- | --- | --- |
| 80 | Insufficient balance | Not until topped up - see `esendex-setup-account` |
| 81 | Daily message limit exceeded | Tomorrow, or raise the limit |
| 82 | Blocked destination address | **No** - permanent |
| 83 | No route available | **No** - permanent |
| 84 | Unrecognised address | **No** - bad number |
| 85 | Missing message part (multipart only) | **No** - client-side concatenation defect |
| 94 | Network submission error | Yes |
| 95 | Other network issue | Yes |
| 97 | Handset incompatible | **No** |
| 112 | Temporary issue | **Yes** |
| 113 | Temporary recipient issue (absent/error) | **Yes** |

Treat any code not in this table as non-retryable and log it instead of looping.

80 and 81 are account problems to fix on the sender's side, and a low-balance alert prevents
80 recurring. 82, 83, 84 and 97 are permanent, so remove the number from the list. 85 points
to a client-side concatenation defect. 94, 95, 112 and 113 can be retried, and Esendex
describes 112 and 113 as temporary.

---

## Common errors

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Bind times out on a new setup | IP allowlisting not yet confirmed | Confirm allowlisting with Technical Services before debugging the client |
| `ESME_RTHROTTLED` (`0x58`) returned; the submission is not queued | More than 5 submit_sm per second on the session | Implement flow control and retransmit; add sessions or use REST throttle schedules for volume |
| Session disconnected | No response to the server's `ENQUIRE_LINK` within its one-minute check | Send keepalives at least once a minute |
| Multipart messages arrive `UNDELIV` with `err:85` | Parts submitted across different binds, or a missing segment | Submit every part of a message over one bind |
| Delivery receipts never arrive | No receiver or transceiver bind, so DLRs queue for 72 hours and are then discarded | Maintain a receiver or transceiver bind |

---

## CANNOT

- **Cannot self-serve the connection details.** Host, port, system_id and password are
  provisioned per customer by Esendex.
- **Cannot connect without prior IP allowlisting.** No bind succeeds before it is confirmed.
- **Cannot use an unsecured connection.** TLS 1.2 or higher, or a requested VPN, only.
- **Cannot exceed 5 submit_sm per second per session.** Submissions over the limit are rejected with `ESME_RTHROTTLED` and are not queued.
- **Cannot split a concatenated message across binds.** Every part goes over the same bind.
- **Cannot use the `sar_*` or `message_payload` TLVs.** Concatenation is UDH only, ESM class 64.
- **Cannot retrieve delivery receipts older than 72 hours without a receiver bind.**
- **Cannot assume the four listed message states are the only ones.** SMPP 3.4 defines others.

---

## Next steps

- `esendex-setup-account` - the account model, balance, limits and sender configuration.
- `esendex-send-message` - the REST alternative, including throttle schedules for volume.
- `esendex-track-delivery` - delivery outcomes, inbound messages and webhooks over REST.
- `esendex-manage-contacts` - contact lists and the opt-out list.
- The Esendex developer docs at https://developer.esendex.co.uk - the SMPP introduction, set-up, sending and message-state pages.

