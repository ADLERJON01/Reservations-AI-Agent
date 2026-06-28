# Gold-set metrics — v2.0.0 taxonomy

Scored **49** emails.

## Facet accuracy

| facet | accuracy | correct/total |
|---|---|---|
| category | 65.3% | 32/49 |
| request_type | 40.8% | 20/49 |
| inquiry_answer_source | 46.9% | 23/49 |
| lifecycle | 71.4% | 35/49 |
| requires_human_followup | 61.2% | 30/49 |
| sender_type | 63.3% | 31/49 |
| urgency_signal | 91.8% | 45/49 |

**Category 65.3% (all) vs v1 enriched 79.6% → -14.3%.** Unambiguous (40): 67.5%. *(Note: v2 has 10 categories vs v1's 7 — a harder task; judge with RAG precision below.)*

## Category precision / recall / F1

| category | P | R | F1 | support |
|---|---|---|---|---|
| booking_notification | 0.60 | 0.50 | 0.55 | 12 |
| sales_availability_or_quote_inquiry | 0.50 | 0.55 | 0.52 | 11 |
| inventory_availability_or_stop_sales | 0.67 | 1.00 | 0.80 | 6 |
| thread_closure_or_acknowledgment | 1.00 | 0.20 | 0.33 | 5 |
| system_or_channel_delivery_exception | 1.00 | 1.00 | 1.00 | 4 |
| booking_change_or_cancellation | 0.40 | 0.67 | 0.50 | 3 |
| knowledge_policy_inquiry | 1.00 | 0.67 | 0.80 | 3 |
| payment_billing_or_rate_issue | 1.00 | 1.00 | 1.00 | 3 |
| guest_service_or_ancillary_request | 1.00 | 1.00 | 1.00 | 2 |
| other_or_unclear | 0.00 | 0.00 | 0.00 | 0 |

**Macro-F1: 0.65**

## RAG-candidate gate (knowledge_policy_inquiry AND kb_policy)

- gold RAG candidates: **2**  |  predicted: **2**
- **precision 100.0%** (TP 2 / TP+FP 2)  |  **recall 100.0%** (TP 2 / TP+FN 2)  |  F1 1.00
- **FALSE RAG candidates (dangerous — would draft from KB) [0]:** none
- missed RAG candidates (escalated instead) [0]: none

## Category misclassifications (17)

- `email_110`: gold **booking_notification** → pred **sales_availability_or_quote_inquiry**
- `email_133`: gold **booking_notification** → pred **sales_availability_or_quote_inquiry**
- `email_157`: gold **thread_closure_or_acknowledgment** → pred **booking_change_or_cancellation**
- `email_162`: gold **booking_notification** → pred **other_or_unclear**
- `email_20`: gold **booking_change_or_cancellation** → pred **booking_notification** [ambiguous]
- `email_204`: gold **thread_closure_or_acknowledgment** → pred **sales_availability_or_quote_inquiry**
- `email_317`: gold **sales_availability_or_quote_inquiry** → pred **booking_notification** [ambiguous]
- `email_324`: gold **thread_closure_or_acknowledgment** → pred **sales_availability_or_quote_inquiry**
- `email_326`: gold **sales_availability_or_quote_inquiry** → pred **inventory_availability_or_stop_sales**
- `email_327`: gold **sales_availability_or_quote_inquiry** → pred **inventory_availability_or_stop_sales**
- `email_337`: gold **sales_availability_or_quote_inquiry** → pred **booking_notification** [ambiguous]
- `email_358`: gold **thread_closure_or_acknowledgment** → pred **booking_change_or_cancellation**
- `email_36`: gold **booking_notification** → pred **sales_availability_or_quote_inquiry**
- `email_368`: gold **knowledge_policy_inquiry** → pred **booking_notification** [ambiguous]
- `email_377`: gold **sales_availability_or_quote_inquiry** → pred **inventory_availability_or_stop_sales**
- `email_72`: gold **booking_notification** → pred **sales_availability_or_quote_inquiry**
- `email_90`: gold **booking_notification** → pred **booking_change_or_cancellation**
