# RB-DB-001: Database Connection-Pool Exhaustion

## Signals

Connection-pool exhaustion commonly causes elevated request latency, HTTP 500 or 503 responses, connection-acquisition timeouts, and an increasing number of waiting requests.

The strongest signal is that active connections equal the configured pool maximum while idle connections remain at zero. The database itself may still be healthy and show moderate CPU utilization.

## Diagnosis

Confirm that the database health check succeeds. Compare active connections with the configured pool maximum and inspect the number of connection waiters.

Search application logs for connection-acquisition timeouts. Review recent deployments for changes to transaction or session handling.

A healthy database combined with a full application pool usually indicates that the application is holding connections too long or failing to release them.

## Likely causes

Common causes include:

- Database sessions not being closed
- Transactions remaining open during external API calls
- A recent change introducing a connection leak
- Queries taking significantly longer than normal
- A pool size that is too small for expected concurrency

## Remediation

Roll back a recent release if the incident began immediately after transaction-handling changes.

Restart affected application instances gradually to release leaked connections. Do not restart every instance simultaneously.

Fix the application so sessions and transactions are always closed. Increasing the pool size may provide temporary relief but does not correct a connection leak.

## Verification

Verify that connection waiters return to zero, idle connections become available, HTTP error rates recover, and checkout latency returns to its normal range.