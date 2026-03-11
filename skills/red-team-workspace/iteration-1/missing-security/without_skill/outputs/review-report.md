# Review: User File Upload Implementation Plan

## Overall Impression

The plan covers the basic flow — upload, store, retrieve, and test. However, there are significant security and operational gaps that need to be addressed before this is implemented.

## Issues

### Path Traversal Vulnerability (Task 2)

Task 2 says: "Look up the file path from the database and use `res.sendFile(path)`." If the stored path is derived from user input at upload time (e.g., the original filename), an attacker could craft a filename like `../../etc/passwd` or `../../../app/.env` to read arbitrary files from the server.

Even if the path is stored in the database, if the upload step (Task 1) stores the user-provided filename directly into the path column without sanitization, the download step will happily serve any file on the filesystem.

**Fix:** Use `path.resolve()` and verify the resolved path starts with the expected uploads directory. Better yet, use generated UUIDs for filenames on disk and store the original filename separately for display purposes.

### Missing Authorization on Downloads

Task 2's GET endpoint looks up a file by `fileId` and serves it. There's no mention of checking whether the requesting user owns that file. Any authenticated user could enumerate file IDs and download other users' files.

**Fix:** Add a `WHERE user_id = req.user.id` clause to the file lookup query, or a separate authorization check before serving the file.

### No File Type Validation

There's no mention of validating file types. The description says "PDFs, spreadsheets" but nothing enforces this. Users could upload executable files, HTML files (which could lead to stored XSS if served with the wrong content type), or other dangerous content.

**Fix:** Validate both the file extension and the MIME type (by inspecting file headers, not just the Content-Type header which is client-controlled). Maintain an allowlist of accepted types.

### No File Size Enforcement on the Server

The plan mentions files "up to 50MB each" but doesn't include server-side enforcement. Without a size limit in the Express middleware (e.g., multer's `limits` option), a user could upload arbitrarily large files and exhaust disk space or memory.

**Fix:** Configure multer (or whatever multipart parser you use) with a `fileSize` limit of 50MB. Return a 413 response if exceeded.

### Local Filesystem Storage

Storing files on the local filesystem (`/uploads/{userId}/{filename}`) has several problems:
- Files are lost if the server is redeployed, the container is replaced, or the disk fails
- You can't scale horizontally — two app instances would have different files
- Disk space is finite and not easily expandable

**Fix:** Use object storage (S3, GCS, Azure Blob) instead. Store the object key in the database, not a local path.

### No Virus/Malware Scanning

Users are uploading arbitrary documents. Without scanning, malicious files could be stored and then distributed to other users who download them.

**Fix:** Integrate a virus scanning step (e.g., ClamAV) after upload before making the file available for download.

### Missing Content-Type Headers on Download

Task 2 doesn't mention setting appropriate `Content-Type` or `Content-Disposition` headers on the response. Serving files without the correct content type could lead to browser-based attacks (e.g., an uploaded HTML file rendered in the browser context of your domain).

**Fix:** Store the file's MIME type in the database and set `Content-Type` appropriately. Always set `Content-Disposition: attachment` to force download rather than inline rendering.

## Summary

The plan has a workable structure but is missing critical security controls. The path traversal vulnerability and missing download authorization are the most serious — either one could lead to unauthorized data access. File type validation, size limits, and moving to object storage should also be addressed before implementation. I'd recommend going back and adding security tasks before writing any code.
