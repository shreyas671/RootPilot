# RB-CACHE-001: Redis Hot Key and Connection Saturation

## Signals

A Redis hot key produces a highly skewed request distribution, rising command latency, timeouts, and exhausted client pools. Connected clients may equal `maxclients` while one key accounts for most requests.

## Diagnosis

Inspect Redis command latency, connected clients, rejected connections, and key-level traffic. Confirm whether a single key receives a disproportionate share of commands. Compare the onset with application changes that altered cache access frequency or removed local request coalescing.

## Likely causes

Common causes include an application rendering loop, a globally popular cache key without sharding, missing request coalescing, an ineffective local cache, or a connection leak in the Redis client.

## Remediation

Roll back the cache access regression or rate-limit the offending request path. Coalesce duplicate reads, add a short-lived local cache, and shard the hot value when appropriate. Increasing `maxclients` is only temporary relief and must not replace fixing the access pattern.

## Verification

Verify that hot-key traffic share, connected clients, Redis command latency, and catalog p99 latency return to their normal ranges without renewed timeouts.
