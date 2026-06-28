# Gold-set metrics

Scored **49** emails.

## Facet accuracy

| facet | accuracy | correct/total |
|---|---|---|
| category | 79.6% | 39/49 |
| sender_type | 69.4% | 34/49 |
| request_type | 44.9% | 22/49 |
| lifecycle | 65.3% | 32/49 |
| expects_human_response | 79.6% | 39/49 |
| urgency_signal | 91.8% | 45/49 |

**Category accuracy on the 28 unambiguous emails: 75.0%** (excludes the 21 flagged `ambiguous`).

## Category precision / recall / F1

| category | P | R | F1 | support |
|---|---|---|---|---|
| service_or_information_inquiry | 0.88 | 0.71 | 0.79 | 21 |
| booking_notification | 0.64 | 0.90 | 0.75 | 10 |
| inventory_availability_or_stop_sales | 0.86 | 1.00 | 0.92 | 6 |
| booking_change_or_cancellation | 0.67 | 0.50 | 0.57 | 4 |
| system_or_channel_delivery_exception | 1.00 | 1.00 | 1.00 | 4 |
| payment_billing_or_rate_issue | 0.75 | 1.00 | 0.86 | 3 |
| other_or_unclear | 0.00 | 0.00 | 0.00 | 1 |

**Macro-F1: 0.70**

## Category misclassifications (10)

- `email_133`: gold **booking_notification** → pred **service_or_information_inquiry**
- `email_151`: gold **booking_change_or_cancellation** → pred **booking_notification**
- `email_157`: gold **service_or_information_inquiry** → pred **payment_billing_or_rate_issue**
- `email_162`: gold **other_or_unclear** → pred **service_or_information_inquiry** [ambiguous]
- `email_20`: gold **booking_change_or_cancellation** → pred **booking_notification** [ambiguous]
- `email_317`: gold **service_or_information_inquiry** → pred **booking_notification**
- `email_327`: gold **service_or_information_inquiry** → pred **inventory_availability_or_stop_sales**
- `email_337`: gold **service_or_information_inquiry** → pred **booking_notification** [ambiguous]
- `email_338`: gold **service_or_information_inquiry** → pred **booking_notification**
- `email_358`: gold **service_or_information_inquiry** → pred **booking_change_or_cancellation**
