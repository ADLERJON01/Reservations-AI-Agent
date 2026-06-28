# Gold-set metrics — taxonomy_v1_1 (v1 7-cat + inquiry_answer_source patch)

Scored **49** emails. Gold category collapsed v2->v1 (7-cat).

## Facet accuracy

| facet | accuracy | correct/total |
|---|---|---|
| category | 81.6% | 40/49 |
| request_type | 65.3% | 32/49 |
| inquiry_answer_source | 63.3% | 31/49 |
| lifecycle | 61.2% | 30/49 |
| requires_human_followup | 73.5% | 36/49 |
| sender_type | 57.1% | 28/49 |
| urgency_signal | 95.9% | 47/49 |

**Category 81.6% (all) | 85.0% (unambiguous).** vs v1 enriched 79.6%, vs v2.1 69.4%.

## Category precision / recall / F1

| category | P | R | F1 | support |
|---|---|---|---|---|
| service_or_information_inquiry | 0.84 | 0.76 | 0.80 | 21 |
| booking_notification | 0.71 | 0.83 | 0.77 | 12 |
| inventory_availability_or_stop_sales | 0.86 | 1.00 | 0.92 | 6 |
| system_or_channel_delivery_exception | 1.00 | 1.00 | 1.00 | 4 |
| booking_change_or_cancellation | 0.67 | 0.67 | 0.67 | 3 |
| payment_billing_or_rate_issue | 1.00 | 0.67 | 0.80 | 3 |

**Macro-F1: 0.83**

## RAG-candidate gate (service_or_information_inquiry AND kb_policy)

- gold candidates: **2** | predicted: **4**
- **precision 50%** (TP 2/4) | **recall 100%** (TP 2/2)
- FALSE candidates (dangerous) [2]: ['email_155', 'email_368']
- missed candidates [0]: none

## Category misclassifications (9)

- `email_133`: gold **booking_notification** → pred **service_or_information_inquiry**
- `email_155`: gold **payment_billing_or_rate_issue** → pred **service_or_information_inquiry**
- `email_157`: gold **service_or_information_inquiry** → pred **booking_change_or_cancellation**
- `email_162`: gold **booking_notification** → pred **service_or_information_inquiry**
- `email_20`: gold **booking_change_or_cancellation** → pred **booking_notification** [ambiguous]
- `email_317`: gold **service_or_information_inquiry** → pred **booking_notification** [ambiguous]
- `email_337`: gold **service_or_information_inquiry** → pred **booking_notification** [ambiguous]
- `email_338`: gold **service_or_information_inquiry** → pred **booking_notification**
- `email_377`: gold **service_or_information_inquiry** → pred **inventory_availability_or_stop_sales**
