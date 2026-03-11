# Code Review: WebhookWorkerPool

## Overview

Looking at this webhook worker pool implementation, there are several concerns I want to flag, particularly around concurrency and scalability given your stated load of 500 events/second.

## Issues Found

### 1. This isn't really a worker pool — it's a sequential queue

Despite the name `WebhookWorkerPool`, this processes events one at a time. The `processing` boolean guard in `processNext()` ensures only one event is handled before the next one starts. At 500 events/second, and assuming each `fetch` call to the callback URL takes even 100ms, you'd process at most 10 events/second. The queue will grow unboundedly and events will be delayed indefinitely.

You need actual concurrency — either run multiple workers (e.g., a pool of N concurrent handlers) or use something like `Promise.all` with a concurrency limiter (e.g., `p-limit`).

### 2. Race condition on the `processing` flag

The `processing` boolean is checked synchronously at the top of `processNext()`, but the method is `async`. Here's the problem: `enqueue()` calls `this.processNext()` without awaiting it. If two events are enqueued in rapid succession, both calls to `processNext()` could read `this.processing` as `false` before either sets it to `true`, because the event loop hasn't yielded yet between the check and the set — actually wait, in this specific code the check and set are synchronous within the same tick, so the classic race doesn't apply in quite the way it would with threads.

However, there IS still an interleaving issue. When `processNext()` finishes processing an event, it sets `this.processing = false` and then calls `this.processNext()` recursively. But if `enqueue()` is called between the `this.processing = false` line and the recursive `this.processNext()` call, the enqueue's own `this.processNext()` call could start a second concurrent processing chain. Now you have two chains both calling `shift()` on the same queue, which could lead to undefined behavior or skipped events.

### 3. Unbounded `results` Map

The `results` Map grows without limit. Every processed event adds an entry, and nothing ever removes them. Over time, this will consume increasing amounts of memory. At 500 events/second, that's 43 million entries per day. This is a memory leak.

You should add a TTL-based eviction strategy, or use an LRU cache, or store results externally (e.g., Redis).

### 4. No retry logic

If a webhook delivery fails (network error, timeout, 5xx response), the event is simply marked as failed and discarded. For webhook delivery, retries with exponential backoff are standard practice. Without retries, transient failures cause permanent data loss for the consumer.

### 5. No timeout on fetch

The `fetch` call has no timeout configured. If the callback URL is slow or unresponsive, the worker will hang indefinitely, blocking all subsequent event processing (since it's sequential).

### 6. Error handling in `catch` block

The catch block accesses `err.message`, but if the error isn't an `Error` instance (e.g., someone throws a string), this will be `undefined`. Minor, but worth a type guard.

### 7. No backpressure

There's no mechanism to apply backpressure when the queue gets too large. If producers are enqueuing at 500/s and processing is far slower, the in-memory queue will grow until the process runs out of memory and crashes.

## Summary

The most critical issue is that this "worker pool" processes one event at a time, making it completely unsuitable for 500 events/second. The race condition on the processing flag, the unbounded results map, and the lack of retries are all significant problems. I'd recommend a substantial redesign before this goes to production — consider an actual concurrent worker pool with bounded concurrency, persistent queue backing (e.g., Redis or a proper message queue), retry logic with exponential backoff, and proper result lifecycle management.
