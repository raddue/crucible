#!/usr/bin/env python3
"""Portable artifact binding; model execution is not verified without host evidence."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
import stat
import struct
import subprocess
import tempfile


def artifact_hash(root: Path, paths, *, deleted=frozenset(), document=False) -> str:
    """Hash exact gated path set; deletion tombstones must be declared explicitly."""
    root = Path(root).resolve()
    names = list(paths)
    removed = set(deleted)
    if not names or len(names) != len(set(names)) or removed - set(names):
        raise ValueError('missing, duplicate or extra gated path')
    for name in names:
        if not isinstance(name, str) or not name or name.startswith('/') or '\\' in name or '\x00' in name or any(part in ('', '.', '..') for part in name.split('/')):
            raise ValueError(f'noncanonical gated path: {name!r}')
    if document and (len(names) != 1 or removed):
        raise ValueError('document requires one existing file')

    common = Path(subprocess.check_output(['git', '-C', str(root), 'rev-parse', '--git-common-dir'], text=True).strip())
    if not common.is_absolute():
        common = root / common
    fields = ['crucible-qg-manifest-v1', str(common.resolve()), str(root), str(len(names))]
    for name in sorted(names, key=lambda value: value.encode('utf-8')):
        path = root / name
        parent = root
        for part in name.split('/')[:-1]:
            parent /= part
            if not stat.S_ISDIR(parent.lstat().st_mode):
                raise ValueError(f'non-directory or symlink parent: {name}')
        if document:
            if not stat.S_ISREG(path.lstat().st_mode):
                raise ValueError('document must be a regular file')
            return hashlib.sha256(path.read_bytes()).hexdigest()
        if name in removed:
            if path.is_symlink() or path.exists():
                raise ValueError(f'deleted path still exists: {name}')
            kind, mode, digest = 'deleted', '-', hashlib.sha256(b'').hexdigest()
        else:
            try:
                info = path.lstat()
            except FileNotFoundError as exc:
                raise ValueError(f'missing gated path: {name}') from exc
            if stat.S_ISLNK(info.st_mode):
                kind, mode, content = 'symlink', '120000', os.fsencode(os.readlink(path))
            elif stat.S_ISREG(info.st_mode):
                kind, mode, content = 'regular', ('100755' if info.st_mode & 0o111 else '100644'), path.read_bytes()
            else:
                raise ValueError(f'unsupported gated file type: {name}')
            digest = hashlib.sha256(content).hexdigest()
        fields.extend((name, kind, mode, digest))
    hasher = hashlib.sha256()
    for value in fields:
        raw = value.encode('utf-8')
        hasher.update(struct.pack('>Q', len(raw)))
        hasher.update(raw)
    return hasher.hexdigest()


MAX_INVENTORY_BYTES = 1_048_576
MAX_INVOCATIONS = 1024


def _validate_inventory(data: dict) -> None:
    try:
        roster = data['roster']
        rows = data['invocations']
        ids = [row['id'] for row in rows]
        valid = (
            data['version'] == 1 and isinstance(data['run_id'], str) and bool(data['run_id'])
            and all(isinstance(data[key], str) and len(data[key]) == 64
                    and all(c in '0123456789abcdef' for c in data[key])
                    for key in ('artifact_hash', 'final_artifact_hash'))
            and roster['kind'] in ('single-artifact', 'chunked')
            and isinstance(roster['chunks'], list) and bool(roster['chunks'])
            and len(roster['chunks']) == len(set(roster['chunks']))
            and set(roster['chunks']) == set(roster['terminal'])
            and len(roster['consensus']) == len(set(roster['consensus']))
            and isinstance(rows, list) and 0 < len(rows) <= MAX_INVOCATIONS
            and len(ids) == len(set(ids)) and all(isinstance(i, str) and i for i in ids)
            and set(roster['consensus']) <= set(ids)
            and all(row['parent'] == data['run_id'] or row['parent'] in ids for row in rows)
            and all(row['scope'] and row['disposition'] in ('consumed', 'unused')
                    and row['assurance'] in ('verified', 'configured', 'unknown') for row in rows)
        )
        if not valid:
            raise ValueError('invalid fields')
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError('invalid or incomplete QG assurance inventory') from exc


def write_inventory(path: Path, data: dict) -> str:
    """Durable, bounded index; its digest proves integrity, not evidence origin."""
    _validate_inventory(data)
    raw = (json.dumps(data, sort_keys=True, separators=(',', ':')) + '\n').encode()
    if len(raw) > MAX_INVENTORY_BYTES:
        raise ValueError('QG assurance inventory exceeds byte limit')
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
            name = tmp.name
            tmp.write(raw)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(name, path)
        with path.open('rb') as saved:
            os.fsync(saved.fileno())
        digest = hashlib.sha256(raw).hexdigest()
        read_inventory(path, digest, data['run_id'], data['artifact_hash'], data['final_artifact_hash'])
        return digest
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def read_inventory(path: Path, digest: str, run_id: str, artifact: str, final_artifact: str) -> dict:
    try:
        with Path(path).open('rb') as saved:
            raw = saved.read(MAX_INVENTORY_BYTES + 1)
        if len(raw) > MAX_INVENTORY_BYTES or hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError('QG assurance inventory digest or size mismatch')
        data = json.loads(raw)
        _validate_inventory(data)
        if (data['run_id'], data['artifact_hash'], data['final_artifact_hash']) != (run_id, artifact, final_artifact):
            raise ValueError('QG assurance inventory binding mismatch')
        return data
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError('QG assurance inventory unavailable or malformed') from exc


def assurance_state(data: dict, policy: dict | None = None) -> str:
    """No host-owned observation exists in portable core; never claim verified."""
    try:
        _validate_inventory(data)
    except ValueError:
        return 'unknown'
    used = [row for row in data['invocations'] if row['disposition'] == 'consumed']
    return ('configured' if used and all(row['assurance'] == 'configured'
            and configured_assurance(row.get('request'), policy) == 'configured' for row in used)
            else 'unknown')


def action_allowed(requirement: str, marker: dict, inventory_path: Path, digest: str,
                   current_final_hash: str, evidence: dict | None = None,
                   allowlist: dict | None = None, policy: dict | None = None) -> bool:
    """Caller predicate: opt-in needs reconciled host evidence; portable default blocks."""
    if requirement == 'none':
        return marker.get('Verdict') == 'PASS'
    if requirement != 'qg-verified' or marker.get('Verdict') != 'PASS':
        return False
    if marker.get('MarkerFinality') != 'final-integration' or marker.get('FinalArtifactHash') != current_final_hash:
        return False
    if marker.get('ModelAssuranceInventory') != f'{inventory_path} sha256:{digest}':
        return False
    try:
        data = read_inventory(inventory_path, digest, marker['RunID'], marker['ArtifactHash'], current_final_hash)
    except (KeyError, ValueError):
        return False
    # Digest and inventory claims cannot attest their own protected origin.
    return (marker.get('ModelAssurance') == 'verified'
            and reconcile_evidence(data, evidence or {}, allowlist or {}, policy or {}) == 'verified')


def configured_assurance(request: dict | None, policy: dict | None) -> str:
    """A matched selector is configured, never independent execution proof."""
    if not request or not policy:
        return 'unknown'
    approved = policy.get(request.get('model'))
    return 'configured' if approved and all(request.get(key) == approved.get(key) for key in ('effort', 'route')) else 'unknown'

def _protected(path: Path, *, key: bool = False) -> bool:
    # shortcut: permission heuristics only — a same-user reviewer child can still forge;
    # real origin protection arrives with the host adapter (#12) owning this area.
    try:
        info = Path(path).lstat()
        parent = Path(path).parent.lstat()
    except OSError:
        return False
    if stat.S_ISLNK(info.st_mode) or stat.S_ISLNK(parent.st_mode):
        return False
    if info.st_mode & (0o077 if key else 0o022) or parent.st_mode & 0o022:
        return False
    return info.st_uid == os.getuid()

def reconcile_evidence(data: dict, evidence: dict | None, allowlist: dict | None, policy: dict | None) -> str:
    """Reconcile host-owned evidence against the inventory; anything unproven is unknown.

    `verified` requires a human-approved allowlist entry, an authenticated protected
    origin (HMAC under a key the reviewer cannot read/write), and per-turn exact-ID
    model/effort/route proof for every consumed invocation. The portable default
    (empty allowlist) fails closed; every failure downgrades, never artifact FAIL.
    """
    try:
        _validate_inventory(data)
        approved = allowlist[evidence['adapter']['name']]
        origin = evidence['origin']
        if approved['version'] != evidence['adapter']['version'] or approved['key_path'] != origin['key_path']:
            return 'unknown'
        key_path = Path(origin['key_path'])
        journal_path = Path(evidence['journal_path'])
        records = evidence['records']
        if evidence['run_id'] != data['run_id']:
            return 'unknown'
        if not all(_protected(path, key=is_key)
                   for path, is_key in [(key_path, True), (journal_path, False)]
                   + [(Path(index['path']), False) for index in records.values()]):
            return 'unknown'
        lines = [json.loads(line) for line in journal_path.read_text().splitlines() if line.strip()]
        if len(lines) > MAX_INVOCATIONS:
            return 'unknown'
        canonical = json.dumps({'journal': lines, 'records': records}, sort_keys=True, separators=(',', ':')).encode()
        keyed = hmac.new(key_path.read_bytes(), canonical, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(keyed, origin['hmac']):
            return 'unknown'
        consumed, seen, results = set(), set(), {}
        for line in lines:
            if line['run_id'] != data['run_id'] or line['id'] in seen:
                return 'unknown'  # wrong binding, or a bridged response counted twice
            seen.add(line['id'])
            if line.get('replay') or line.get('rollback'):
                continue
            if line['disposition'] not in ('consumed', 'unused'):
                return 'unknown'
            if line['disposition'] == 'consumed':
                consumed.add(line['id'])
                results[line['id']] = line['result_digest']
        expected = {row['id'] for row in data['invocations'] if row['disposition'] == 'consumed'}
        if consumed != expected or set(records) != consumed or not set(data['roster']['consensus']) <= consumed:
            return 'unknown'
        for row in data['invocations']:
            if row['disposition'] != 'consumed':
                continue
            raw = Path(records[row['id']]['path']).read_bytes()
            if len(raw) > MAX_INVENTORY_BYTES or hashlib.sha256(raw).hexdigest() != records[row['id']]['digest']:
                return 'unknown'
            record = json.loads(raw)
            if (record['id'] != row['id'] or record['result_digest'] != results[row['id']]
                    or not record['turns']
                    or any(configured_assurance(turn, policy) != 'configured' for turn in record['turns'])):
                return 'unknown'
        return 'verified'
    except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError):
        return 'unknown'
