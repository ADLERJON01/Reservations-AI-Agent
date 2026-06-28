# Gold-set metrics — v2.0.0 taxonomy

Scored **49** emails.

## Facet accuracy

| facet | accuracy | correct/total |
|---|---|---|
| category | 69.4% | 34/49 |
| request_type | 49.0% | 24/49 |
| inquiry_answer_source | 59.2% | 29/49 |
| lifecycle | 67.3% | 33/49 |
| requires_human_followup | 71.4% | 35/49 |
| sender_type | 75.5% | 37/49 |
| urgency_signal | 95.9% | 47/49 |

**Category 69.4% (all) vs v1 enriched 79.6% → -10.2%.** Unambiguous (40): 72.5%. *(Note: v2 has 10 categories vs v1's 7 — a harder task; judge with RAG precision below.)*

## Category precision / recall / F1

| category | P | R | F1 | support |
|---|---|---|---|---|
| booking_notification | 0.69 | 0.75 | 0.72 | 12 |
| sales_availability_or_quote_inquiry | 0.62 | 0.45 | 0.53 | 11 |
| inventory_availability_or_stop_sales | 0.67 | 1.00 | 0.80 | 6 |
| thread_closure_or_acknowledgment | 0.43 | 0.60 | 0.50 | 5 |
| system_or_channel_delivery_exception | 1.00 | 1.00 | 1.00 | 4 |
| booking_change_or_cancellation | 0.67 | 0.67 | 0.67 | 3 |
| knowledge_policy_inquiry | 1.00 | 0.33 | 0.50 | 3 |
| payment_billing_or_rate_issue | 1.00 | 0.67 | 0.80 | 3 |
| guest_service_or_ancillary_request | 1.00 | 1.00 | 1.00 | 2 |

**Macro-F1: 0.72**

## RAG-candidate gate (knowledge_policy_inquiry AND kb_policy)

- gold RAG candidates: **2**  |  predicted: **1**
- **precision 100.0%** (TP 1 / TP+FP 1)  |  **recall 50.0%** (TP 1 / TP+FN 2)  |  F1 0.67
- **FALSE RAG candidates (dangerous — would draft from KB) [0]:** none
- missed RAG candidates (escalated instead) [1]: ['email_4']

## Category misclassifications (15)

- `email_110`: gold **booking_notification** → pred **sales_availability_or_quote_inquiry**
- `email_133`: gold **booking_notification** → pred **sales_availability_or_quote_inquiry**
- `email_155`: gold **payment_billing_or_rate_issue** → pred **thread_closure_or_acknowledgment**
- `email_157`: gold **thread_closure_or_acknowledgment** → pred **booking_change_or_cancellation**
- `email_162`: gold **booking_notification** → pred **thread_closure_or_acknowledgment**
- `email_20`: gold **booking_change_or_cancellation** → pred **booking_notification** [ambiguous]
- `email_317`: gold **sales_availability_or_quote_inquiry** → pred **booking_notification** [ambiguous]
- `email_324`: gold **thread_closure_or_acknowledgment** → pred **booking_notification**
- `email_325`: gold **sales_availability_or_quote_inquiry** → pred **thread_closure_or_acknowledgment**
- `email_326`: gold **sales_availability_or_quote_inquiry** → pred **inventory_availability_or_stop_sales**
- `email_335`: gold **sales_availability_or_quote_inquiry** → pred **thread_closure_or_acknowledgment**
- `email_337`: gold **sales_availability_or_quote_inquiry** → pred **booking_notification** [ambiguous]
- `email_368`: gold **knowledge_policy_inquiry** → pred **inventory_availability_or_stop_sales** [ambiguous]
- `email_377`: gold **sales_availability_or_quote_inquiry** → pred **inventory_availability_or_stop_sales**
- `email_4`: gold **knowledge_policy_inquiry** → pred **sales_availability_or_quote_inquiry**
