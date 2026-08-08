# RB-KAFKA-001: Kafka Consumer Lag and Poison Events

## Signals

A poison event is a message that a consumer cannot deserialize or validate. The consumer may repeatedly restart and return to the same partition and offset.

Typical signals include rapidly increasing consumer lag, a very low processing rate, repeated worker restarts, and identical validation errors for the same offset.

## Diagnosis

Confirm that Kafka brokers and the topic are healthy. Identify which partition is accumulating lag and inspect the consumer logs for the failing offset.

If every restart returns to the same offset, inspect that event’s schema and compare it with the schema supported by the consumer.

Review recent producer changes, particularly new event versions or required-field changes.

## Likely causes

Common causes include:

- A producer publishing an incompatible schema version
- A required field being removed or renamed
- Invalid JSON or corrupted message content
- Consumer validation being stricter than the producer contract
- Missing backward-compatibility handling

## Remediation

Pause consumption for the affected partition and preserve the failing event for investigation.

Quarantine or skip the invalid event only through an approved operational procedure. Update the consumer to support the new schema, or restore the producer’s compatible event format.

Resume consumption and confirm that the consumer advances beyond the failing offset.

## Verification

Verify that the processed offset advances, consumer lag decreases, worker restarts stop, and pending orders begin processing normally.