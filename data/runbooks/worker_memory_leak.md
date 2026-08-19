# RB-MEMORY-001: Worker Memory Leak and OOM Restarts

## Signals

A worker memory leak appears as steadily increasing resident memory that does not fall after work completes, followed by Kubernetes `OOMKilled` terminations, exit code 137, repeated pod restarts, and a growing work queue.

## Diagnosis

Compare working-set memory with the container limit over time and correlate restarts with queue growth. Review recent releases involving native libraries or large buffers. Use heap or allocation profiling on a canary and confirm whether completed tasks release decoder objects and byte buffers.

## Likely causes

Common causes include a native decoder leak, retained buffers, unbounded in-process caches, missing stream closure, or concurrency that permits too many large images to be decoded simultaneously.

## Remediation

Roll back the suspected decoder release and reduce worker concurrency to stabilize the queue. Restart workers gradually for temporary recovery. Fix object and buffer lifecycle, place bounds on caches, and add memory regression tests before redeployment.

## Verification

Verify that memory reaches a stable plateau under sustained load, pod restarts stop, completed tasks release memory, and the image queue drains at the expected rate.
