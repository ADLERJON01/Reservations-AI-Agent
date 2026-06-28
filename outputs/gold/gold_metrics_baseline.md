# Gold-set metrics

Scored **49** emails.

## Facet accuracy

| facet | accuracy | correct/total |
|---|---|---|
| category | 59.2% | 29/49 |
| sender_type | 59.2% | 29/49 |
| request_type | 44.9% | 22/49 |
| lifecycle | 71.4% | 35/49 |
| expects_human_response | 77.6% | 38/49 |
| urgency_signal | 93.9% | 46/49 |

**Category accuracy on the 28 unambiguous emails: 42.9%** (excludes the 21 flagged `ambiguous`).

## Category precision / recall / F1

| category | P | R | F1 | support |
|---|---|---|---|---|
| service_or_information_inquiry | 1.00 | 0.24 | 0.38 | 21 |
| booking_notification | 0.62 | 0.80 | 0.70 | 10 |
| inventory_availability_or_stop_sales | 0.55 | 1.00 | 0.71 | 6 |
| booking_change_or_cancellation | 0.23 | 0.75 | 0.35 | 4 |
| system_or_channel_delivery_exception | 1.00 | 1.00 | 1.00 | 4 |
| payment_billing_or_rate_issue | 1.00 | 0.67 | 0.80 | 3 |
| other_or_unclear | 1.00 | 1.00 | 1.00 | 1 |

**Macro-F1: 0.71**

## Category misclassifications (20)

- `email_157`: gold **service_or_information_inquiry** → pred **booking_change_or_cancellation**
- `email_161`: gold **service_or_information_inquiry** → pred **booking_change_or_cancellation** [ambiguous]
- `email_20`: gold **booking_change_or_cancellation** → pred **inventory_availability_or_stop_sales** [ambiguous]
- `email_204`: gold **service_or_information_inquiry** → pred **inventory_availability_or_stop_sales**
- `email_297`: gold **booking_notification** → pred **booking_change_or_cancellation** [ambiguous]
- `email_317`: gold **service_or_information_inquiry** → pred **booking_notification**
- `email_324`: gold **service_or_information_inquiry** → pred **booking_change_or_cancellation**
- `email_325`: gold **service_or_information_inquiry** → pred **booking_notification**
- `email_326`: gold **service_or_information_inquiry** → pred **inventory_availability_or_stop_sales**
- `email_327`: gold **service_or_information_inquiry** → pred **inventory_availability_or_stop_sales**
- `email_335`: gold **service_or_information_inquiry** → pred **booking_change_or_cancellation**
- `email_336`: gold **service_or_information_inquiry** → pred **booking_notification**
- `email_337`: gold **service_or_information_inquiry** → pred **booking_notification** [ambiguous]
- `email_338`: gold **service_or_information_inquiry** → pred **booking_notification**
- `email_358`: gold **service_or_information_inquiry** → pred **booking_change_or_cancellation**
- `email_368`: gold **service_or_information_inquiry** → pred **booking_change_or_cancellation**
- `email_376`: gold **service_or_information_inquiry** → pred **booking_change_or_cancellation**
- `email_377`: gold **service_or_information_inquiry** → pred **inventory_availability_or_stop_sales**
- `email_90`: gold **booking_notification** → pred **booking_change_or_cancellation**
- `email_99`: gold **payment_billing_or_rate_issue** → pred **booking_change_or_cancellation**
