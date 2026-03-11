I'm using the red-team skill to adversarially review this artifact.

---

# Red Team Report: User File Upload Implementation Plan

## Artifact Under Review

An implementation plan for adding file upload/download functionality to an Express.js + PostgreSQL + React web application. The plan covers upload endpoint, download endpoint, database schema, UI component, and integration tests. Expected usage: ~200 users uploading PDFs and spreadsheets up to 50MB each.

---

## Fatal Challenges

### F1. Path Traversal Vulnerability in the Download Endpoint (Task 2)

**What breaks:** Task 2 specifies: "Look up the file path from the database and use `res.sendFile(path)`." The file path stored in the database originates from user input (the uploaded filename in Task 1: `/uploads/{userId}/{filename}`). If the `path` column in the `files` table contains a traversal sequence, `res.sendFile()` will serve arbitrary files from the server's filesystem.

**Attack scenario:**
1. Attacker uploads a file with a crafted filename like `../../../etc/passwd` or `....//....//etc/shadow`.
2. Task 1 saves the file to `/uploads/{userId}/../../etc/passwd` — but more critically, stores this path (or a variant) in the `files` table.
3. When any user requests `GET /api/files/{fileId}`, the server calls `res.sendFile("/uploads/123/../../etc/passwd")`, which resolves to `/etc/passwd` and serves the system password file.

Even if the upload step sanitizes filenames (which the plan does not specify), the stored `path` in the database is the critical control point. If an attacker gains SQL write access or the upload sanitization is bypassed, the download endpoint becomes an arbitrary file read vulnerability.

Express's `res.sendFile()` does resolve relative paths, and without a `root` option, it operates relative to the process's working directory. A path containing `../` will traverse out of the intended directory.

**Evidence:** Task 2: "Look up the file path from the database and use `res.sendFile(path)`." Task 1: "Save the uploaded file to the local filesystem under `/uploads/{userId}/{filename}`." Neither task mentions path sanitization or validation.

**Impact:** Full server filesystem read access. An attacker can read `/etc/passwd`, environment files (`.env` with database credentials), application source code, private keys, and any other file readable by the Node.js process.

**Proposed fix:**
1. **Sanitize filenames on upload:** Strip all path separators and traversal sequences. Use `path.basename()` to extract only the filename, then generate a UUID-based filename to avoid collisions and eliminate user-controlled path components entirely:
   ```typescript
   const safeFilename = `${uuidv4()}${path.extname(originalFilename)}`;
   const filePath = path.join('/uploads', userId, safeFilename);
   ```
2. **Constrain `res.sendFile()` with a root option:**
   ```typescript
   res.sendFile(filename, { root: '/uploads' });
   ```
3. **Validate the resolved path** before serving:
   ```typescript
   const resolvedPath = path.resolve(storedPath);
   if (!resolvedPath.startsWith('/uploads/')) {
     return res.status(403).send('Forbidden');
   }
   ```

### F2. Missing Authorization on File Downloads — Any Authenticated User Can Access Any User's Files

**What breaks:** Task 2 specifies: "Add a GET /api/files/{fileId} endpoint that returns the file." The plan states that JWT auth middleware exists on all `/api` routes, which verifies the user is *authenticated*. However, there is no mention of *authorization* — checking that the authenticated user owns the requested file.

**Attack scenario:**
1. User A uploads a confidential document. It is stored as file ID 42.
2. User B (also authenticated) requests `GET /api/files/42`.
3. The endpoint looks up file ID 42 in the database, finds the path, and serves it to User B.
4. User B now has User A's confidential document.

Since `fileId` is likely a sequential integer (the plan uses `id` as PK), an attacker can enumerate all file IDs by incrementing the number: `GET /api/files/1`, `GET /api/files/2`, etc., downloading every file in the system.

**Evidence:** Task 2 only specifies looking up the file path from the database by `fileId`. Task 3's data model includes `user_id` in the `files` table but Task 2 never references it. The plan says "We use JWT auth middleware on all /api routes" but this only proves authentication, not per-file authorization.

**Impact:** Complete breach of file confidentiality. Any authenticated user can access any other user's files. With ~200 users uploading sensitive documents (PDFs, spreadsheets), this is a direct data breach vector.

**Proposed fix:** Add ownership verification in the download endpoint:
```typescript
app.get('/api/files/:fileId', authMiddleware, async (req, res) => {
  const file = await db('files').where({ id: req.params.fileId }).first();
  if (!file) return res.status(404).send('Not found');
  if (file.user_id !== req.user.id) return res.status(403).send('Forbidden');
  // ... serve file
});
```

---

## Significant Challenges

### S1. No File Type Validation — Arbitrary File Upload

**What the risk is:** Task 1 accepts "multipart form data" with no restriction on file types. The plan mentions the expected usage is "PDFs, spreadsheets" but does not enforce this. Without file type validation:

- An attacker can upload executable files (`.exe`, `.sh`, `.bat`), HTML files with embedded JavaScript (stored XSS), or `.php`/`.jsp` files that could be executed if the server is misconfigured.
- Malicious files (malware, viruses) can be stored and served to other users (if the authorization issue in F2 is not fixed, or even to the uploading user themselves on a different device).
- SVG files with embedded JavaScript can cause XSS when rendered in the browser.

**Likelihood:** High. Without validation, any file type is accepted by default.

**Impact:** Stored XSS, malware distribution, potential remote code execution if upload directory is web-accessible.

**Proposed fix:**
1. Validate file extension against an allowlist: `['.pdf', '.xlsx', '.xls', '.csv', '.doc', '.docx']`.
2. Validate MIME type from the `Content-Type` header AND by inspecting file magic bytes (use a library like `file-type`), since MIME type headers can be spoofed.
3. Set `Content-Disposition: attachment` on the download response to prevent browser rendering of uploaded content:
   ```typescript
   res.setHeader('Content-Disposition', `attachment; filename="${file.originalFilename}"`);
   ```

### S2. Local Filesystem Storage — Not Scalable, Not Durable

**What the risk is:** Task 1 stores files to the local filesystem at `/uploads/{userId}/{filename}`. This has multiple problems:

1. **No durability:** If the server is redeployed, rebooted, or replaced (standard in containerized/cloud deployments), all uploaded files are lost. There is no backup or replication.
2. **No horizontal scaling:** If the application runs on multiple instances (behind a load balancer), each instance has its own local filesystem. A file uploaded to instance A cannot be downloaded from instance B.
3. **Disk exhaustion:** With 200 users uploading 50MB files, even modest usage (50 files per user) consumes 500GB. Local disks have hard limits, and there is no monitoring or quota management.

**Likelihood:** Near-certain in any modern deployment pipeline (Docker, Kubernetes, cloud VMs with ephemeral storage).

**Impact:** Data loss on redeployment, download failures in multi-instance deployments.

**Proposed fix:** Use object storage (AWS S3, GCP Cloud Storage, or Azure Blob Storage):
```typescript
// Upload
const key = `uploads/${userId}/${uuidv4()}${path.extname(filename)}`;
await s3.putObject({ Bucket: 'app-uploads', Key: key, Body: fileStream });

// Download
const signedUrl = await s3.getSignedUrl('getObject', {
  Bucket: 'app-uploads', Key: file.s3Key, Expires: 300
});
res.redirect(signedUrl);
```
Store the S3 key in the database instead of a local path. This provides durability, horizontal scaling, and eliminates local disk management.

### S3. No Server-Side File Size Enforcement

**What the risk is:** The plan mentions files "up to 50MB each" but does not specify server-side size limits. Without server-side enforcement:

- An attacker can upload multi-gigabyte files, exhausting server memory (since Express/multer loads the file into memory by default) or disk space.
- This is a denial-of-service vector: a single request with a 10GB payload can crash the server or fill the disk.
- Client-side size limits (if any exist in the React component) are trivially bypassed with `curl` or any HTTP client.

**Likelihood:** High. This is a well-known attack vector for file upload endpoints.

**Impact:** Denial of service via resource exhaustion.

**Proposed fix:** Configure multer (or whatever multipart middleware is used) with a server-side size limit:
```typescript
const upload = multer({
  limits: {
    fileSize: 50 * 1024 * 1024, // 50MB
    files: 1,
  },
  dest: '/uploads/tmp/',
});

app.post('/api/files', authMiddleware, upload.single('file'), async (req, res) => {
  // ...
});
```

Also consider adding a per-user storage quota (e.g., 1GB per user) tracked in the database.

### S4. No Virus/Malware Scanning

**What the risk is:** The application accepts file uploads from users and serves them back, acting as a file hosting service. Without malware scanning, the system can become a vector for malware distribution. An attacker uploads a malware-laden PDF; a legitimate user (or the attacker's target) downloads it and gets infected.

**Likelihood:** Medium. Depends on the application's user base and exposure.

**Impact:** The platform becomes complicit in malware distribution. Potential legal liability and reputational damage.

**Proposed fix:** Integrate a virus scanning step before making files available for download:
- Use ClamAV (open source) via the `clamscan` library for Node.js.
- Scan files after upload but before setting their status to "available" in the database.
- Quarantine or delete files that fail scanning.
- Alternatively, use a cloud-based scanning service (e.g., AWS has built-in S3 malware scanning via GuardDuty).

---

## Minor Observations

- **No mention of CORS configuration for the upload endpoint.** If the API and frontend are on different origins, multipart uploads may be blocked by CORS policies. Non-blocking but will surface during testing.
- **The `files` table uses `filename` from the user.** This should store both the original filename (for display) and a sanitized/UUID-based storage filename (for actual file access). Storing only the user-provided filename risks collisions when two users upload files with the same name.
- **No upload progress indication mentioned in the UI component (Task 4).** For 50MB files on slow connections, uploads can take minutes. A progress bar is expected UX. Non-blocking.
- **Integration tests (Task 5) don't mention testing error cases.** The plan says "Write integration tests for upload and download" but doesn't specify testing size limits, invalid file types, unauthorized access, or malformed requests. Tests should cover failure modes, not just happy paths.
- **No mention of cleaning up files when database records are deleted.** If a file record is deleted from the database, the physical file remains on disk (or in S3), becoming an orphan. A cleanup mechanism (e.g., a scheduled job or a cascade delete hook) is needed.

---

## Overall Assessment

- **Verdict:** Has fundamental issues that must be addressed before implementation
- **Confidence:** High. The path traversal vulnerability (F1) and missing download authorization (F2) are concrete, exploitable security flaws — not theoretical risks. The path traversal is a standard OWASP Top 10 vulnerability, and the missing authorization is trivially exploitable by any authenticated user. These are verified against the plan's own specification: no sanitization is mentioned, no ownership check is specified, and `res.sendFile(path)` is explicitly called with a database-stored path.
- **Summary:** This plan handles the happy path but entirely omits security. The two Fatal issues (path traversal and missing download authorization) are exploitable vulnerabilities that would expose the server filesystem and all users' files to any authenticated user. The Significant issues (no file type validation, local storage, no size limits, no malware scanning) compound the risk. Before implementation, the plan needs: filename sanitization with UUID-based storage names, ownership verification on downloads, file type allowlisting, server-side size limits, and a migration from local filesystem to object storage. The security issues must be addressed in the plan itself, not deferred to implementation — otherwise they will be missed.
