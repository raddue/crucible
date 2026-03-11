# Design: Offline-First Field Inspection App

## Overview

This document describes the design for an offline-first React Native mobile app used by field inspectors at construction sites. Inspectors fill out inspection forms, capture photos, collect signatures, and sync everything when connectivity is available. The backend is Django REST API with PostgreSQL. A key challenge is that multiple inspectors may visit the same site and edit overlapping data.

## Architecture Overview

```
Mobile App (React Native)
  |-- Local DB (WatermelonDB on SQLite)
  |-- Photo Storage (filesystem)
  |-- Sync Engine
        |-- Form Data Sync (JSON deltas)
        |-- Binary Upload (photos, signatures)
        |-- Conflict Resolution
  |
  v
Django REST API
  |-- Sync Endpoints
  |-- Conflict Resolution Service
  |-- PostgreSQL
  |-- S3 / Object Storage (photos)
```

## Local Storage Strategy

**Recommendation: WatermelonDB** (built on SQLite)

WatermelonDB is the best fit for this use case because:

1. **Built for React Native** with lazy loading — it won't load all records into memory, which matters when inspectors accumulate hundreds of inspections with photos over time.
2. **Built-in sync primitives** — it has a push/pull sync protocol designed specifically for offline-first apps.
3. **Observable queries** — the UI reactively updates when local data changes, which is important for the form-filling experience.
4. **SQLite underneath** — battle-tested, reliable, no data corruption concerns.

**Alternatives considered:**
- **Raw SQLite (via `react-native-sqlite-storage`):** More control but requires building all the sync infrastructure from scratch. Not worth it.
- **Realm:** Good offline support but adds vendor lock-in with MongoDB ecosystem. The team is using PostgreSQL on the backend.
- **AsyncStorage:** Not appropriate for structured relational data with queries.

### Local Schema

```
inspections
  - id (UUID, generated locally)
  - site_id (FK)
  - inspector_id (FK)
  - form_template_id (FK)
  - status (draft | completed | synced)
  - started_at
  - completed_at
  - updated_at
  - _sync_status (created | updated | synced)
  - _version (integer, incremented on each local edit)

inspection_fields
  - id (UUID)
  - inspection_id (FK)
  - field_key (string, e.g., "foundation_condition")
  - field_value (text/JSON)
  - updated_at
  - updated_by (inspector_id)
  - _sync_status
  - _version

photos
  - id (UUID)
  - inspection_id (FK)
  - field_key (optional, ties photo to a specific form field)
  - local_uri (filesystem path)
  - remote_url (null until uploaded)
  - caption
  - taken_at
  - upload_status (pending | uploading | uploaded | failed)
  - _sync_status

signatures
  - id (UUID)
  - inspection_id (FK)
  - signer_name
  - signer_role (inspector | site_manager | client)
  - signature_data (base64 PNG or SVG path data)
  - signed_at
  - device_id
  - _sync_status
```

## Sync Protocol

### Change Tracking

Every record has:
- `_sync_status`: tracks whether it's `created`, `updated`, or `synced` locally.
- `_version`: integer version counter, incremented on every local edit.
- `updated_at`: timestamp of last modification.

The server also tracks versions. When syncing, the client sends its last known server timestamp and receives all changes since then.

### Sync Flow

The sync process runs in three phases:

#### Phase 1: Pull (Server -> Client)
```
GET /api/sync/pull?last_synced_at=2026-03-10T14:30:00Z
```

Response includes all records modified on the server since the given timestamp. The client applies these changes to local DB, triggering conflict resolution if needed.

#### Phase 2: Push Form Data (Client -> Server)
```
POST /api/sync/push
{
  "changes": {
    "inspections": {
      "created": [...],
      "updated": [...],
      "deleted": [...]
    },
    "inspection_fields": {
      "created": [...],
      "updated": [...]
    },
    "signatures": {
      "created": [...]
    }
  },
  "client_timestamp": "2026-03-10T15:00:00Z"
}
```

The server processes changes within a transaction, applying conflict resolution rules, and returns the results (accepted, merged, or rejected for each record).

#### Phase 3: Upload Binaries (Photos & Signatures)
Photos and signature images are uploaded separately and asynchronously:

```
POST /api/sync/upload
Content-Type: multipart/form-data
- file: <binary>
- record_id: <UUID>
- record_type: "photo" | "signature"
```

**Why separate binary upload?**
- Form data is small (KB) and can sync quickly even on weak connections.
- Photos can be 5-15 MB each. Mixing them with form sync would block critical data.
- Binary uploads can be resumed independently if interrupted.
- The app tracks upload status per photo so the user sees progress.

### Sync Order Matters

1. Pull first, so we have the latest server state before pushing.
2. Push form data second, so the server can process conflicts with full context.
3. Upload binaries last, since they're referenced by already-synced records.

If the app loses connectivity during sync, each phase is independently resumable:
- Pull is idempotent (same timestamp returns same results).
- Push uses the record UUIDs as idempotency keys — re-pushing the same record is a no-op if the version matches.
- Binary uploads check `upload_status` per file and skip already-uploaded files.

## Conflict Resolution

This is the core challenge: two inspectors visit the same site and edit overlapping inspection data.

### Strategy: Field-Level Merge with Last-Write-Wins per Field

We use **field-level merging** rather than record-level last-write-wins. This is important because:

- Inspector A might update `foundation_condition` while Inspector B updates `electrical_status` on the same inspection. These are independent changes and should both be preserved.
- Record-level LWW would lose one inspector's entire set of changes.
- Full CRDTs are overkill for form data — we don't need character-level merging of text fields.

### How It Works

Each `inspection_field` record tracks `updated_at` and `updated_by`. During sync push:

1. Server compares the incoming field's `_version` with the server's version.
2. If the server version hasn't changed since the client last pulled, the update is accepted.
3. If the server version is newer (another inspector modified the same field):
   - **For non-text fields** (dropdowns, checkboxes, ratings): last-write-wins based on `updated_at`. The later timestamp wins.
   - **For text fields** (notes, comments): if both modified, the server keeps both values and marks the field as `conflicted`. The next inspector to open the form sees both values and manually resolves.
   - **For photos**: photos are additive. Both inspectors' photos are kept. No conflict.

### Conflict Notification

When the server detects and auto-resolves a conflict, it returns metadata in the sync response:

```json
{
  "conflicts_resolved": [
    {
      "record_type": "inspection_field",
      "record_id": "...",
      "field_key": "foundation_condition",
      "resolution": "server_wins",
      "your_value": "Good",
      "kept_value": "Needs Repair",
      "other_inspector": "Jane Smith"
    }
  ]
}
```

The app displays a toast notification: "Jane Smith also updated Foundation Condition. Their value was kept. Tap to review."

## Partial Sync Recovery

Sync can fail at any point. Here's how each failure is handled:

| Failure Point | Recovery |
|---|---|
| Pull fails midway | Re-pull with same `last_synced_at`. Idempotent. |
| Push fails before server response | Re-push. Server uses UUIDs + versions as idempotency keys. |
| Push succeeds but client doesn't get response | Client re-pushes. Server detects duplicate and returns success. |
| Photo upload fails | Photo stays in `pending` or `failed` status. Next sync retries. |
| App crashes during sync | On restart, sync status flags on records are still accurate. Sync restarts from the beginning. |

All sync operations are designed to be **idempotent**. Pushing the same change twice never creates duplicates.

## Photo Handling

### Capture
- Use `react-native-camera` or `expo-camera` for photo capture.
- Photos are saved to the app's document directory (not camera roll) for persistence.
- Metadata (GPS coordinates from device, timestamp, inspection reference) is attached at capture time.
- Photos are compressed to 80% quality JPEG, max 2048px on longest side, to balance quality vs. storage/upload size.

### Storage
- Stored locally on the filesystem with a reference in the SQLite database.
- Old synced photos can be cleaned up from local storage after confirmation (keep last 30 days locally).

### Upload
- Photos upload in a background queue, one at a time.
- Each upload is individually tracked (`pending` -> `uploading` -> `uploaded` or `failed`).
- Failed uploads retry up to 3 times with exponential backoff.
- On the server, photos go directly to S3 (or equivalent object storage) via a presigned URL to avoid loading the Django server with large binary transfers.

### Presigned URL Flow
1. Client requests upload URL: `POST /api/sync/upload-url` with file metadata.
2. Server returns a presigned S3 PUT URL (valid for 15 minutes).
3. Client uploads directly to S3.
4. Client confirms upload: `POST /api/sync/upload-confirm` with the S3 key.
5. Server verifies and links the photo to the inspection record.

## Signature Capture

### Capture
- Use `react-native-signature-canvas` for signature input.
- Signatures are captured as SVG path data (vector) for small file size and resolution independence.
- A PNG rasterization is also generated for display purposes.

### Legal Validity

To ensure signatures have evidentiary value:

1. **Timestamp**: The exact `signed_at` time is recorded (device clock + any known server time offset from last sync).
2. **Device ID**: The unique device identifier is stored alongside the signature.
3. **Signer identification**: Name and role of the signer are recorded.
4. **Immutability**: Once a signature record is created, it cannot be edited or deleted locally — only new signatures can be added.
5. **Audit trail**: The server logs all signature-related events (created, synced, viewed) with timestamps.
6. **Hash integrity**: A SHA-256 hash of the signature data + metadata is computed at capture time and verified on the server to detect tampering.

### Storage
- Signature SVG data is stored in the local database (it's small, typically < 10 KB).
- The PNG rasterization is stored as a file, uploaded with the same binary upload flow as photos.

## Offline UX Considerations

- **Sync status indicator**: A persistent icon showing connection status and sync state (synced, pending changes, syncing, error).
- **Queue visibility**: Users can see how many items are pending upload (e.g., "3 photos waiting to upload").
- **Manual sync trigger**: A "Sync Now" button in addition to automatic sync when connectivity is detected.
- **Stale data warning**: If data hasn't synced in > 24 hours, show a warning banner.
- **Offline-created inspections**: Fully functional. UUIDs are generated client-side so no server round-trip is needed to create records.

## Backend Sync Endpoints (Django)

```
GET  /api/sync/pull?last_synced_at=<ISO timestamp>
POST /api/sync/push
POST /api/sync/upload-url
POST /api/sync/upload-confirm
GET  /api/sync/status  (returns server time + user's sync health)
```

All sync endpoints require authentication via JWT token. The token is cached locally and refreshed on sync.

## Summary

Key design decisions:

1. **WatermelonDB** for local storage — purpose-built for React Native offline-first apps with sync primitives.
2. **Field-level merge** for conflict resolution — preserves independent edits from multiple inspectors without losing data.
3. **Three-phase sync** (pull, push data, upload binaries) — ensures critical form data syncs fast while large photos upload independently.
4. **Idempotent operations throughout** — partial sync failures recover cleanly without duplicates.
5. **Presigned S3 URLs** for photo uploads — offloads binary transfer from the Django server.
6. **Signature audit trail** with hash integrity — ensures legal defensibility of captured signatures.
