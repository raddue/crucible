# Offline-First Field Inspection App — Design

**Date:** 2026-03-11
**Status:** Draft
**Tech Stack:** React Native (mobile), Django REST API (backend), PostgreSQL
**Domain:** Construction site inspections with offline capability
**Key Challenge:** Offline data capture, multi-inspector conflict resolution, photo/signature sync

---

## Phase 1: Context Gathering

### Understanding the Domain

Field inspectors visit construction sites where internet connectivity is unreliable or absent. They need to:
- Fill out structured inspection forms (checklists, measurements, text notes)
- Attach photos to inspection items
- Capture signatures (site manager, inspector)
- Sync everything when back online

Multiple inspectors may visit the same site and edit overlapping data (e.g., two inspectors on different floors of the same building, both updating the same overall site record).

The backend is an existing Django REST API with PostgreSQL. We're building the mobile client with React Native.

Key complexity drivers:
- **Offline-first** — the app must be fully functional without connectivity
- **Conflict resolution** — overlapping edits from multiple inspectors
- **Large binary data** — photos must sync without blocking form data
- **Legal requirements** — signatures need audit trails for compliance

---

## Phase 2: Investigated Questions

### Design Dimension 1: Local Storage Strategy

**Hypothesis:** I expect WatermelonDB (built on SQLite) to be the best fit since it's designed specifically for React Native offline-first apps with sync capabilities. Realm is a strong alternative but adds vendor lock-in. Raw SQLite via `expo-sqlite` would work but requires building sync logic from scratch.

#### Investigation (Deep Dive)

**Codebase Scout:**
No existing React Native codebase — this is a new mobile app. The backend is Django REST with PostgreSQL. The local storage choice is unconstrained by existing patterns.

**Domain Researcher:**
Four viable local storage options:

1. **WatermelonDB** — Built on SQLite, designed for React Native. Has a built-in sync protocol (`synchronize()`) with push/pull semantics. Lazy-loading architecture handles large datasets well. Active community.
   - Advantages: Built-in sync adapter matches our Django pull/push model; optimized for React Native performance; observable queries for reactive UI
   - Disadvantages: Sync protocol is opinionated — may not fit our conflict resolution needs perfectly; requires a specific backend sync endpoint shape
   - Complexity: Medium — the sync adapter handles the hard parts

2. **Realm (MongoDB)** — Full database with object-oriented API. Realm Sync is powerful but ties you to MongoDB Atlas backend.
   - Advantages: Excellent offline performance; rich query API; automatic conflict resolution
   - Disadvantages: Vendor lock-in to MongoDB Atlas (we use PostgreSQL/Django); Realm Sync doesn't work with arbitrary backends; large binary size
   - Complexity: High — would require replacing or proxying the Django backend

3. **SQLite via `op-sqlite` or `expo-sqlite`** — Raw SQLite access. Maximum flexibility.
   - Advantages: No vendor lock-in; full control over schema and sync; smallest bundle size; battle-tested
   - Disadvantages: Must build entire sync protocol from scratch; no reactive queries without wrapping
   - Complexity: High — sync logic is the hardest part, and we'd build it ourselves

4. **MMKV + JSON blobs** — Key-value store, very fast for simple data.
   - Advantages: Extremely fast reads/writes; simple API
   - Disadvantages: No relational queries; poor fit for structured inspection data with relationships; no built-in sync
   - Complexity: Low for storage, high for sync

| Approach | Sync Built-in | Backend Fit | Complexity | Performance |
|----------|--------------|-------------|-----------|-------------|
| WatermelonDB | Yes (adaptable) | Good | Medium | Excellent |
| Realm | Yes (Atlas only) | Poor (wrong backend) | High | Excellent |
| Raw SQLite | No | Perfect (full control) | High | Good |
| MMKV | No | N/A | Low storage / High sync | Excellent (simple data) |

**Recommendation:** WatermelonDB. Its sync protocol is adaptable to work with our Django backend (we implement the pull/push endpoints). It handles the hard parts (change tracking, batched sync, lazy loading) while giving us enough flexibility for custom conflict resolution.

**Impact Analyst:**
- WatermelonDB requires specific Django endpoints: `POST /sync/pull` (server sends changes since timestamp) and `POST /sync/push` (client sends local changes)
- Schema must be defined both in WatermelonDB models (client) and Django models (server) — keep them aligned
- Photo storage is separate from WatermelonDB — binary data stored on filesystem, referenced by ID in the database

**Challenge:**
Solid recommendation. One concern: WatermelonDB's built-in sync protocol uses timestamp-based change tracking, which can miss changes if device clocks are skewed. For multi-inspector scenarios, consider augmenting with server-assigned version numbers rather than relying solely on client timestamps. Also: WatermelonDB's conflict resolution is last-write-wins by default — fine for some fields, but dangerous for inspection status fields where an inspector might overwrite another's findings.

**Surprises:** Realm's complete incompatibility with non-MongoDB backends was expected but worth confirming — it eliminates what would otherwise be the strongest option. The challenger's point about clock skew is important and feeds into the conflict resolution decision.

#### Decision: WatermelonDB with Server-Assigned Versions

- WatermelonDB for local structured data storage
- Server-assigned monotonic version numbers for change tracking (not client timestamps)
- Photos stored on device filesystem, referenced by UUID in WatermelonDB records
- Custom sync adapter wrapping WatermelonDB's `synchronize()` to add our conflict resolution logic

**Cascading context for subsequent decisions:** We're using WatermelonDB with server-assigned versions. Conflict resolution must work within WatermelonDB's sync adapter model (pull/push). Photos are stored separately from the database.

---

### Design Dimension 2: Conflict Resolution Strategy

**Hypothesis:** Given that multiple inspectors edit overlapping data, we need field-level merge rather than whole-record last-write-wins. I expect a hybrid approach: field-level merge for independent fields (e.g., one inspector updates the "electrical" section while another updates "plumbing") with conflict flagging for truly overlapping edits on the same field.

#### Investigation (Deep Dive)

**Codebase Scout:**
The Django backend uses PostgreSQL. Django REST Framework supports partial updates (`PATCH`) which aligns with field-level tracking. No existing sync or conflict resolution patterns.

**Domain Researcher:**
Three approaches for conflict resolution in an offline-first inspection context:

1. **Last-Write-Wins (LWW) — whole record:**
   - How it works: Whichever change has the latest timestamp overwrites the entire record
   - Advantage: Simplest to implement
   - Disadvantage: Catastrophic for inspections — Inspector A's electrical findings get silently overwritten by Inspector B's plumbing update because B synced later
   - Verdict: **Unacceptable** for this domain

2. **Field-Level Merge with LWW per field:**
   - How it works: Track changes at the field level. Each field has its own version/timestamp. During sync, merge non-conflicting field changes automatically. For same-field conflicts, latest write wins.
   - Advantage: Handles the common case (different inspectors updating different sections) automatically
   - Disadvantage: Same-field conflicts still use LWW — acceptable if conflicts are rare and an audit trail exists
   - Complexity: Medium — requires field-level change tracking on both client and server

3. **Field-Level Merge with Manual Conflict Resolution:**
   - How it works: Same as #2, but when two inspectors change the same field, the second sync flags a conflict and presents both versions to the user for manual resolution.
   - Advantage: No data loss, ever
   - Disadvantage: Inspectors in the field may not have context to resolve another inspector's conflict immediately; queue of unresolved conflicts can grow
   - Complexity: High — requires conflict queue UI, resolution workflow

4. **CRDTs (Conflict-Free Replicated Data Types):**
   - How it works: Data structures that mathematically guarantee convergence without conflicts
   - Advantage: True conflict-free merging
   - Disadvantage: Massive overkill for structured forms; CRDTs excel at text editing but add enormous complexity for simple field updates; team would need deep CRDT expertise
   - Verdict: **Over-engineered** for this use case

| Approach | Data Safety | Complexity | User Burden | Fit |
|----------|-----------|-----------|------------|-----|
| LWW (record) | Poor | Low | None | Unacceptable |
| Field-level LWW | Good | Medium | None | Good |
| Field-level + manual | Excellent | High | Moderate | Best for critical fields |
| CRDTs | Excellent | Very High | None | Over-engineered |

**Recommendation:** Hybrid — field-level merge with LWW for most fields, manual conflict resolution for critical fields (inspection status, pass/fail decisions, compliance findings). This matches the domain: most edits are to different sections and merge automatically, but safety-critical findings require human review when conflicts occur.

**Impact Analyst:**
- Requires field-level change tracking in WatermelonDB — track which fields changed in each sync batch
- Django backend needs a merge endpoint that processes field-level diffs
- Critical fields list must be configurable (not hardcoded) — different inspection types have different critical fields
- Conflict queue UI in the app — inspectors see "3 conflicts to review" on sync

**Challenge:**
Good hybrid approach. One concern: defining "critical fields" requires domain expertise from the inspection team, not the engineering team. Ship with a sensible default (status fields, pass/fail, compliance notes are critical; measurements and timestamps are LWW) but make it admin-configurable. Also: what happens when a conflict exists on a critical field but both inspectors are now offline again? The conflict must be stored locally and synced later.

**Surprises:** The challenger's point about offline conflict resolution is sharp — conflicts can be created and then the inspector who needs to resolve them goes offline again. The conflict queue must itself be offline-capable. This wasn't in my hypothesis.

#### Decision: Hybrid Field-Level Merge

- **Non-critical fields** (measurements, timestamps, general notes): Field-level LWW — latest version wins automatically
- **Critical fields** (inspection status, pass/fail, compliance findings, safety flags): Conflict flagged for manual resolution
- **Critical fields list:** Admin-configurable per inspection template, stored in app config
- **Conflict queue:** Stored locally in WatermelonDB, syncs with server, resolvable offline
- **Change tracking:** Each sync payload includes `changed_fields: ["field_a", "field_b"]` and `field_versions: { "field_a": 5, "field_b": 3 }`
- **Server merge logic:** Django receives push, compares field versions, auto-merges non-conflicting fields, creates conflict records for critical field clashes

**Cascading context update:** We use field-level merge with hybrid LWW/manual resolution. Change tracking is per-field with server-assigned versions. Conflicts are stored locally and synced.

---

### Design Dimension 3: Sync Protocol & Partial Sync Recovery

**Hypothesis:** Given WatermelonDB's pull/push model and our field-level conflict resolution, the sync protocol will be: pull server changes first (to get latest versions), then push local changes. For partial failure recovery, each push should be idempotent and the client should track which records were successfully pushed.

#### Investigation (Deep Dive)

**Codebase Scout:**
Django REST Framework supports batch operations. PostgreSQL transactions ensure atomicity. WatermelonDB's `synchronize()` function expects pull then push ordering.

**Domain Researcher:**
Sync protocol design for offline-first with large data:

**Pull Phase (server → client):**
1. Client sends `last_pulled_at` version number
2. Server returns all records created, updated, or deleted since that version
3. Client applies changes to local WatermelonDB

**Push Phase (client → server):**
1. Client sends all locally created, updated, and deleted records since last successful push
2. Server processes each record: creates, merges (field-level), or deletes
3. Server returns success/conflict status per record
4. Client marks successfully pushed records as synced

**Partial failure handling approaches:**

| Approach | How | Trade-off |
|----------|-----|-----------|
| All-or-nothing transaction | Entire push in one DB transaction | Simple but one bad record blocks all |
| Per-record transactions | Each record in its own transaction | Resilient but many small transactions |
| Batch with checkpoint | Process in batches of 50, checkpoint after each batch | Good balance |

**Recommendation:** Per-record processing with batch transport. Send all changes in one HTTP request (efficient), but the server processes and responds per-record. A failed record doesn't block others. Client retries only failed records on next sync.

**Impact Analyst:**
- Django endpoint needs to return per-record status: `{ "results": [{ "id": "abc", "status": "ok" }, { "id": "def", "status": "conflict", "conflict": {...} }] }`
- Client must track per-record sync status in WatermelonDB (custom `_sync_status` field)
- Idempotency: server must handle duplicate pushes gracefully (same record pushed twice = no-op if version matches)
- Network interruption mid-push: client doesn't know which records the server received. Idempotency handles this — safe to re-push everything.

**Challenge:**
Solid design. One gap: what's the maximum payload size for a push? An inspector who's been offline for a week might have hundreds of form records. The single HTTP request approach could time out. Consider: if push payload exceeds a threshold (e.g., 100 records or 1MB), chunk it into multiple requests with a sync session ID to maintain atomicity guarantees.

**Surprises:** The chunking concern is valid — I underestimated the payload size issue for long-offline inspectors. Adding chunking with a sync session.

#### Decision: Pull-Then-Push with Per-Record Processing and Chunking

**Sync flow:**

```
1. Client: POST /api/sync/pull { last_version: 1042 }
   Server: { changes: { inspections: { created: [...], updated: [...], deleted: [...] }, ... }, current_version: 1087 }

2. Client applies server changes to local DB

3. Client: POST /api/sync/push { sync_session: "uuid", chunk: 1, total_chunks: 3, changes: [...] }
   Server: { results: [{ id: "abc", status: "ok" }, { id: "def", status: "conflict", conflict: {...} }] }

4. Repeat step 3 for remaining chunks

5. Client: POST /api/sync/push/complete { sync_session: "uuid" }
   Server: { new_version: 1090 }

6. Client updates last_version to 1090
```

**Idempotency:** Server stores `(sync_session, record_id)` pairs. Duplicate pushes are no-ops.

**Chunking:** 50 records per chunk or 500KB, whichever is hit first. Photos are excluded from this (separate sync, next decision).

**Retry:** On network failure, client retries the current chunk. On app restart, client checks for incomplete sync sessions and resumes.

**Cascading context update:** Sync uses pull/push with per-record processing, chunked transport, and sync sessions for recovery. Form data syncs separately from photos.

---

### Design Dimension 4: Photo Handling During Sync

**Hypothesis:** Photos must sync separately from form data to avoid blocking inspection sync. I expect a background upload queue where photos are uploaded individually, and form records reference photos by UUID regardless of upload status.

#### Investigation (Quick Scan)

**Codebase Scout / Domain Researcher:**
Standard approach for large binary sync in offline-first apps:

1. **Reference-first pattern:** Form data includes `photo_id: "uuid"` references. Photos upload independently. Server accepts form data even if referenced photos haven't arrived yet.
2. **Upload queue:** Photos are queued for upload with retry logic. Background upload continues even when the app is backgrounded (React Native background fetch / background upload).
3. **Compression:** Photos compressed client-side before upload (JPEG quality 80%, max dimension 2048px). Reduces upload size by 60-80%.
4. **Progressive availability:** Server shows placeholder for missing photos, replaces with actual image when upload completes.

This is well-established practice with no real alternatives — auto-resolving.

#### Decision — Auto-Resolved: Background Photo Upload Queue

Only one viable approach: decouple photo uploads from form sync.

- Photos stored on device filesystem at capture time, referenced by UUID in WatermelonDB
- Background upload queue (using `react-native-background-upload`) processes photos independently
- Photos compressed client-side: JPEG quality 80%, max 2048px on longest edge
- Upload endpoint: `PUT /api/photos/{uuid}` (idempotent — safe to retry)
- Server returns `200` even if form data referencing the photo hasn't arrived yet (eventual consistency)
- Client tracks upload status per photo: `pending → uploading → uploaded → confirmed`
- If upload fails 3 times, photo is flagged for manual retry in the UI
- Server-side: photos stored in S3-compatible object storage (not PostgreSQL), referenced by UUID

*Speak up if you disagree.*

**Cascading context update:** Photos sync via a separate background queue, decoupled from form data. References are by UUID. Server accepts references to not-yet-uploaded photos.

---

### Design Dimension 5: Offline Signature Capture

**Hypothesis:** Signatures will be captured as SVG paths or bitmap images, stored locally with metadata (timestamp, device ID, signer identity) for legal audit trail. The legal validity concern primarily requires tamper-evidence — we need to hash the inspection data at signing time and store that hash with the signature.

#### Investigation (Deep Dive)

**Codebase Scout:**
React Native has several signature libraries: `react-native-signature-canvas` (most popular, captures as SVG or base64 PNG), `react-native-signature-pad`. No existing patterns in this codebase.

**Domain Researcher:**
Signature capture for legal validity in construction inspections:

**Capture format:**
- SVG paths: Small file size, infinitely scalable, preservable as data. Best for storage and rendering.
- Base64 PNG: Larger but universally compatible. Better for PDF report generation.
- Recommendation: Capture as SVG, render to PNG for reports.

**Legal validity requirements:**
Construction inspection signatures need to be defensible in disputes (insurance claims, safety investigations). Key requirements:
1. **Identity of signer:** Name, role, and relationship to the inspection
2. **Timestamp:** When the signature was applied (device time + timezone)
3. **Content hash:** SHA-256 hash of the inspection data at the moment of signing — proves the inspection wasn't modified after signing
4. **Device identification:** Device ID, app version — establishes which device captured the signature
5. **Tamper evidence:** The content hash makes post-signing modification detectable

**What's NOT required:**
- Digital certificates (PKI) — overkill for construction inspections
- Blockchain — unnecessary
- Biometric verification — not standard practice

**Impact Analyst:**
- Content hash at signing time means the inspection form must be "frozen" when signed — no further edits to signed fields
- This creates a state machine: `draft → signed_by_inspector → countersigned_by_manager → finalized`
- Signed inspections that need correction require a formal "amendment" record, not an edit
- The signature metadata (hash, device ID, timestamp) must be included in the sync payload

**Challenge:**
Solid approach. Key concern: if the inspection is signed offline and then syncs with conflicts on non-critical fields (LWW resolution), the content hash will no longer match the server version. Solution: the content hash must be computed on the canonical form at signing time, and the server must store the original signed version alongside any merged version. Two versions: "as-signed" (immutable, hash-verified) and "current" (post-merge).

**Surprises:** The challenger identified a critical interaction between signatures and conflict resolution that I missed. The "as-signed" vs. "current" version distinction is essential — without it, our conflict resolution system would invalidate signatures.

#### Decision: SVG Signatures with Content Hash and Dual Versioning

**Capture:**
- Use `react-native-signature-canvas` to capture SVG path data
- Store signature as SVG string in WatermelonDB
- Render to PNG for PDF report generation

**Audit trail per signature:**
```json
{
  "signature_svg": "<svg>...</svg>",
  "signer_name": "Jane Smith",
  "signer_role": "Lead Inspector",
  "signed_at": "2026-03-11T14:30:00-05:00",
  "device_id": "iPhone-ABC123",
  "app_version": "1.2.0",
  "content_hash": "sha256:abc123...",
  "inspection_snapshot_id": "uuid"
}
```

**Content hash:**
- Computed on the canonical JSON representation of all inspection fields at signing time
- SHA-256 hash stored with signature record
- Server stores the "as-signed" inspection snapshot (immutable) alongside the "current" version

**State machine:**
`draft` → `inspector_signed` → `manager_countersigned` → `finalized`
- Signed inspections cannot be edited — only amended (creates a new amendment record referencing the original)
- Amendments require re-signing

**Cascading context update:** Signatures include content hashes. Signed inspections are immutable. Server maintains "as-signed" snapshots separate from merged "current" versions.

---

## Phase 3: Design Presentation

### Architecture Overview

```
┌─────────────────────────────────────────┐
│           React Native App              │
│                                         │
│  ┌─────────────┐  ┌─────────────────┐  │
│  │ WatermelonDB│  │ Photo Filesystem│  │
│  │ (SQLite)    │  │ Storage         │  │
│  └──────┬──────┘  └───────┬─────────┘  │
│         │                 │             │
│  ┌──────┴─────────────────┴──────────┐  │
│  │         Sync Engine               │  │
│  │  - Pull/Push protocol             │  │
│  │  - Field-level change tracking    │  │
│  │  - Conflict queue management      │  │
│  │  - Photo upload queue             │  │
│  └──────────────┬────────────────────┘  │
│                 │                        │
└─────────────────┼────────────────────────┘
                  │ HTTPS
┌─────────────────┼────────────────────────┐
│                 │    Django Backend       │
│  ┌──────────────┴─────────────────────┐  │
│  │         Sync API                   │  │
│  │  POST /api/sync/pull               │  │
│  │  POST /api/sync/push               │  │
│  │  PUT  /api/photos/{uuid}           │  │
│  └─────────────┬──────────────────────┘  │
│                │                          │
│  ┌─────────────┴───┐  ┌──────────────┐  │
│  │   PostgreSQL    │  │  S3 (Photos) │  │
│  └─────────────────┘  └──────────────┘  │
└──────────────────────────────────────────┘
```

### Data Model (Client — WatermelonDB)

```javascript
// models/Inspection.js
class Inspection extends Model {
  static table = 'inspections'
  static associations = {
    inspection_items: { type: 'has_many', foreignKey: 'inspection_id' },
    signatures: { type: 'has_many', foreignKey: 'inspection_id' },
    photos: { type: 'has_many', foreignKey: 'inspection_id' },
  }

  @text('site_id') siteId
  @text('inspector_id') inspectorId
  @text('status') status  // draft, inspector_signed, manager_countersigned, finalized
  @text('inspection_type') inspectionType
  @json('form_data', sanitize) formData
  @readonly @date('created_at') createdAt
  @date('updated_at') updatedAt
  @json('field_versions', sanitize) fieldVersions  // { "status": 5, "form_data.electrical": 3 }
  @text('sync_status') syncStatus  // synced, pending, conflict
}

// models/InspectionItem.js
class InspectionItem extends Model {
  static table = 'inspection_items'
  @relation('inspections', 'inspection_id') inspection
  @text('category') category  // electrical, plumbing, structural, fire_safety
  @text('item_name') itemName
  @text('result') result  // pass, fail, n_a, needs_review
  @text('notes') notes
  @json('measurements', sanitize) measurements
  @json('field_versions', sanitize) fieldVersions
}

// models/Signature.js
class Signature extends Model {
  static table = 'signatures'
  @relation('inspections', 'inspection_id') inspection
  @text('signature_svg') signatureSvg
  @text('signer_name') signerName
  @text('signer_role') signerRole
  @text('signed_at') signedAt
  @text('device_id') deviceId
  @text('app_version') appVersion
  @text('content_hash') contentHash
  @text('snapshot_id') snapshotId
}

// models/Photo.js
class Photo extends Model {
  static table = 'photos'
  @relation('inspections', 'inspection_id') inspection
  @text('local_path') localPath
  @text('remote_url') remoteUrl  // null until uploaded
  @text('upload_status') uploadStatus  // pending, uploading, uploaded, failed
  @text('caption') caption
  @date('taken_at') takenAt
}
```

### Data Model (Server — Django)

```python
class Inspection(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    site = models.ForeignKey('Site', on_delete=models.CASCADE)
    inspector = models.ForeignKey('User', on_delete=models.CASCADE)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='draft')
    inspection_type = models.CharField(max_length=50)
    form_data = models.JSONField(default=dict)
    field_versions = models.JSONField(default=dict)  # Server-assigned monotonic versions
    version = models.IntegerField(default=0)  # Global record version
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class InspectionSnapshot(models.Model):
    """Immutable copy of inspection at signing time"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    inspection = models.ForeignKey(Inspection, on_delete=models.CASCADE)
    snapshot_data = models.JSONField()  # Full inspection state at signing time
    content_hash = models.CharField(max_length=64)  # SHA-256
    created_at = models.DateTimeField(auto_now_add=True)

class ConflictRecord(models.Model):
    """Tracks unresolved field-level conflicts"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    inspection = models.ForeignKey(Inspection, on_delete=models.CASCADE)
    field_path = models.CharField(max_length=200)
    server_value = models.JSONField()
    client_value = models.JSONField()
    server_version = models.IntegerField()
    client_version = models.IntegerField()
    resolved = models.BooleanField(default=False)
    resolved_by = models.ForeignKey('User', null=True, on_delete=models.SET_NULL)
    resolved_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
```

### Sync Engine (Client-Side)

```javascript
// sync/engine.js
async function performSync() {
  const lastVersion = await getLastSyncVersion();

  // Phase 1: Pull
  const pullResponse = await api.post('/sync/pull', {
    last_version: lastVersion,
    tables: ['inspections', 'inspection_items', 'signatures', 'photos']
  });

  await database.write(async () => {
    await applyServerChanges(pullResponse.changes);
  });

  // Phase 2: Push (chunked)
  const localChanges = await getLocalChanges();
  const chunks = chunkChanges(localChanges, { maxRecords: 50, maxBytes: 500000 });
  const syncSession = uuid();

  for (const [index, chunk] of chunks.entries()) {
    const pushResponse = await api.post('/sync/push', {
      sync_session: syncSession,
      chunk: index + 1,
      total_chunks: chunks.length,
      changes: chunk
    });

    await processConflicts(pushResponse.results);
    await markSynced(pushResponse.results.filter(r => r.status === 'ok'));
  }

  // Phase 3: Complete
  const completeResponse = await api.post('/sync/push/complete', {
    sync_session: syncSession
  });

  await setLastSyncVersion(completeResponse.new_version);
}

// Photo sync runs independently
async function syncPhotos() {
  const pendingPhotos = await getPendingPhotos();
  for (const photo of pendingPhotos) {
    try {
      await backgroundUpload(photo.localPath, `/api/photos/${photo.id}`);
      await photo.update(record => { record.uploadStatus = 'uploaded'; });
    } catch (e) {
      await photo.update(record => {
        record.uploadStatus = record.retryCount >= 3 ? 'failed' : 'pending';
      });
    }
  }
}
```

### Merge Logic (Server-Side)

```python
# sync/merge.py
def merge_record(server_record, client_changes, critical_fields):
    """Field-level merge with hybrid LWW/manual resolution."""
    conflicts = []
    merged_data = dict(server_record.form_data)
    merged_versions = dict(server_record.field_versions)

    for field, client_value in client_changes['fields'].items():
        client_version = client_changes['field_versions'].get(field, 0)
        server_version = server_record.field_versions.get(field, 0)

        if client_version > server_version:
            # Client is newer — accept
            merged_data[field] = client_value
            merged_versions[field] = client_version
        elif client_version == server_version and client_value != getattr_nested(server_record.form_data, field):
            # Same version but different values — concurrent edit
            if field in critical_fields:
                # Critical field — flag conflict for manual resolution
                conflicts.append(ConflictRecord(
                    inspection=server_record,
                    field_path=field,
                    server_value=getattr_nested(server_record.form_data, field),
                    client_value=client_value,
                    server_version=server_version,
                    client_version=client_version
                ))
            else:
                # Non-critical — LWW (server wins, but timestamp-based if available)
                pass  # Keep server value
        # else: client is older — ignore

    server_record.form_data = merged_data
    server_record.field_versions = merged_versions
    server_record.version += 1
    server_record.save()

    ConflictRecord.objects.bulk_create(conflicts)
    return {'status': 'conflict' if conflicts else 'ok', 'conflicts': conflicts}
```

---

## Gap Scan

- [x] **Acceptance criteria** — Offline data capture, multi-inspector sync, conflict resolution, photo handling, and signature capture are all specified with concrete implementations.
- [x] **Testing strategy:**
  - Unit tests: WatermelonDB model serialization, field-level merge logic, content hash computation
  - Integration tests: Full sync cycle (create offline → sync → verify server state), conflict generation and resolution, chunked push with interruption recovery
  - E2E tests: Offline form fill → airplane mode off → sync → verify on second device
  - Edge case tests: Clock skew between devices, very large inspection (100+ photos), sync interruption at every chunk boundary
- [x] **Integration impact** — Django backend needs new sync endpoints, S3 bucket for photos, background upload integration in React Native
- [x] **Failure modes:**
  - Network drops during push → sync session tracks progress, resumes from last successful chunk
  - Photo upload fails repeatedly → flagged in UI, inspector can retry manually or sync on Wi-Fi
  - Server rejects push due to version mismatch → client re-pulls, re-applies local changes, retries push
  - Device storage full → warn at 80% capacity, prioritize text data sync over photos
  - App killed during sync → on restart, check for incomplete sync sessions and resume
- [x] **Edge cases:**
  - Inspector signs an inspection, goes offline, another inspector edits it server-side → "as-signed" snapshot is preserved, current version diverges, amendment required
  - Two inspectors create new inspections for the same site simultaneously → no conflict (different records), both sync fine
  - Inspector deletes a photo locally that was already uploaded → soft delete syncs to server, S3 cleanup via background job
  - Very long offline period (weeks) → large sync payload handled by chunking; version numbers are monotonic, no overflow concern
  - Signature SVG exceeds typical size (complex signature) → cap at 500KB, simplify path data on capture
