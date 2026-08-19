# RB-TLS-001: TLS Certificate Expiration

## Signals

Certificate expiration causes sudden TLS handshake failures, x509 expiry messages, and near-total request failure while process and network health checks may remain normal. Failures often begin exactly at the certificate's `notAfter` timestamp.

## Diagnosis

Inspect the certificate chain served by the failing endpoint and compare the leaf and intermediate expiration timestamps with the incident start. Confirm the expected certificate is mounted and that automated renewal and reload jobs completed successfully.

## Likely causes

Likely causes include a failed renewal job, a renewed certificate that was never deployed, a process that did not reload the new certificate, an expired intermediate, or monitoring that did not alert before expiration.

## Remediation

Issue and deploy a valid certificate through the approved certificate-management process. Reload or roll the gateway safely, validate the complete chain, and replay queued webhook deliveries. Repair renewal automation rather than relying on manual rotation.

## Verification

Verify the served certificate chain and expiration date from an external client, confirm TLS handshakes succeed, and ensure webhook delivery success and queue depth recover.
