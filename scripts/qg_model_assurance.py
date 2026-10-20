#!/usr/bin/env python3
"""Portable artifact binding; model execution is not verified without host evidence."""
from __future__ import annotations

import hashlib
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

    if document:
        # A single document is hashed before (and without) any git lookup so a non-git root works.
        try:
            parent = root
            for part in names[0].split('/')[:-1]:
                parent /= part
                if not stat.S_ISDIR(parent.lstat().st_mode):
                    raise ValueError(f'non-directory or symlink parent: {names[0]}')
            if not stat.S_ISREG((root / names[0]).lstat().st_mode):
                raise ValueError('document must be a regular file')
            return hashlib.sha256((root / names[0]).read_bytes()).hexdigest()
        except OSError as exc:
            raise ValueError('document unavailable') from exc

    try:
        common = Path(subprocess.check_output(['git', '-C', str(root), 'rev-parse', '--git-common-dir'],
                                              text=True, stderr=subprocess.DEVNULL).strip())
    except (subprocess.CalledProcessError, OSError) as exc:
        raise ValueError('not a git worktree: cannot bind the gated manifest') from exc
    if not common.is_absolute():
        common = root / common
    fields = ['crucible-qg-manifest-v1', str(common.resolve()), str(root), str(len(names))]
    for name in sorted(names, key=lambda value: value.encode('utf-8')):
        path = root / name
        parent = root
        for part in name.split('/')[:-1]:
            parent /= part
            try:
                is_dir = stat.S_ISDIR(parent.lstat().st_mode)
            except FileNotFoundError:
                if name in removed:  # a tombstone under a wholly deleted directory
                    break
                raise ValueError(f'missing gated parent directory: {name}')
            if not is_dir:
                raise ValueError(f'non-directory or symlink parent: {name}')
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
                kind, mode, content = 'regular', ('100755' if info.st_mode & stat.S_IXUSR else '100644'), path.read_bytes()
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
TERMINAL_STATUSES = ('PASS', 'STAGNATION', 'ESCALATED', 'ARCHITECTURAL', 'SUSTAINED_REGRESSION')


def _hex64(value) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def _valid_request(request) -> bool:
    """A row's optional `request` (the exact model/effort/route the dispatch asked for): absent, or str fields."""
    return request is None or (isinstance(request, dict) and all(
        isinstance(request.get(key), str) for key in ('model', 'effort', 'route') if key in request))


def _validate_inventory(data: dict, *, terminal: bool = False) -> None:
    """Provisional (mid-run, writable as the run proceeds) vs terminal (marker emit / caller check).

    Provisional: any subset of chunks terminal, `final_artifact_hash`/`gated` may still be null.
    Terminal: every chunk has a checked terminal status, the final hash and gated path set are
    frozen, every row carries a non-empty `kind` (consensus rows `consensus-member` /
    `consensus-synthesis`, any mode), and every mandatory consensus member is a consumed row.
    """
    try:
        roster = data['roster']
        rows = data['invocations']
        ids = [row['id'] for row in rows]
        chunks, status, consensus = roster['chunks'], roster['terminal'], roster['consensus']
        gated = data.get('gated')
        valid = (
            type(data['version']) is int and data['version'] == 1 and isinstance(data['run_id'], str) and bool(data['run_id'])
            and _hex64(data['artifact_hash'])
            and roster['kind'] in ('single-artifact', 'chunked')
            and isinstance(chunks, list) and bool(chunks) and len(chunks) == len(set(chunks))
            and isinstance(status, dict) and set(status) <= set(chunks)
            and all(value in TERMINAL_STATUSES for value in status.values())
            and isinstance(consensus, list) and len(consensus) == len(set(consensus))
            and isinstance(rows, list) and 0 < len(rows) <= MAX_INVOCATIONS
            and len(ids) == len(set(ids)) and all(isinstance(i, str) and i for i in ids)
            and set(consensus) <= set(ids)
            and all(row['parent'] == data['run_id'] or row['parent'] in ids for row in rows)
            and all(row['scope'] and row['disposition'] in ('consumed', 'unused')
                    and row['assurance'] in ('verified', 'configured', 'unknown') for row in rows)
            and all(_hex64(row['attestation'].get('digest')) and _hex64(row['attestation'].get('result_digest'))
                    for row in rows if row['assurance'] == 'verified')
            and (data['final_artifact_hash'] is None or _hex64(data['final_artifact_hash']))
            and (gated is None or (isinstance(gated['paths'], list) and isinstance(gated['deleted'], list)
                                   and all(isinstance(n, str) for n in gated['paths'] + gated['deleted'])
                                   and gated['mode'] in ('document', 'manifest')
                                   and (gated['mode'] == 'manifest'
                                        or (len(gated['paths']) == 1 and not gated['deleted']))))
            and all(isinstance(row.get('kind', ''), str) for row in rows)
            and all(_valid_request(row.get('request')) for row in rows)
        )
        if valid and terminal:
            consumed = {row['id'] for row in rows if row['disposition'] == 'consumed'}
            valid = (_hex64(data['final_artifact_hash']) and gated is not None and bool(gated['paths'])
                     and all(isinstance(row.get('kind'), str) and row['kind'] for row in rows)
                     and set(gated['deleted']) <= set(gated['paths'])
                     and set(status) == set(chunks) and set(consensus) <= consumed)
        if not valid:
            raise ValueError('invalid fields')
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ValueError('invalid or incomplete QG assurance inventory') from exc


def gated_hash(data: dict, root: Path) -> str:
    """The only FinalArtifactHash computation: artifact_hash over the inventory's persisted gated set.

    The hash mode (`document` raw bytes of a single file, or `manifest`) is read from the
    persisted `gated.mode`, never guessed by the caller.

    Hashes the working tree at `root`; a caller revalidating a commit must have a clean tree at
    that commit. In manifest mode the hash binds `root`, so a different checkout fails closed (document mode hashes raw bytes only).
    """
    gated = data['gated']
    return artifact_hash(root, gated['paths'], deleted=frozenset(gated['deleted']),
                         document=gated['mode'] == 'document')


def write_inventory(path: Path, data: dict, *, terminal: bool = False) -> str:
    """Durable, bounded index; its digest proves integrity, not evidence origin."""
    _validate_inventory(data, terminal=terminal)
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
        dir_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
        digest = hashlib.sha256(raw).hexdigest()
        read_inventory(path, digest, data['run_id'], data['artifact_hash'],
                       data['final_artifact_hash'] if terminal else None)
        return digest
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def read_inventory(path: Path, digest: str | None, run_id: str, artifact: str, final_artifact: str | None) -> dict:
    """Terminal read (final_artifact given): digest, binding and terminal schema all required.

    Provisional read (final_artifact None): mid-run recovery only, no marker digest exists yet;
    `digest` may be None and the result is never an assurance-bearing closure input.
    """
    terminal = final_artifact is not None
    try:
        if terminal and digest is None:
            raise ValueError('terminal read requires the marker digest')
        with Path(path).open('rb') as saved:
            raw = saved.read(MAX_INVENTORY_BYTES + 1)
        if len(raw) > MAX_INVENTORY_BYTES or (digest is not None and hashlib.sha256(raw).hexdigest() != digest):
            raise ValueError('QG assurance inventory digest or size mismatch')
        data = json.loads(raw)
        _validate_inventory(data, terminal=terminal)
        if (data['run_id'], data['artifact_hash']) != (run_id, artifact) or (
                terminal and data['final_artifact_hash'] != final_artifact):
            raise ValueError('QG assurance inventory binding mismatch')
        return data
    except (OSError, UnicodeError, RecursionError, json.JSONDecodeError) as exc:
        raise ValueError('QG assurance inventory unavailable or malformed') from exc


def assurance_state(data: dict, policy: dict | None = None) -> str:
    """No host-owned observation exists in portable core; never claim verified.

    Total: any malformed inventory, request or policy reads `unknown`, never raises, so it
    can never block marker emit for an ordinary PASS.
    """
    try:
        _validate_inventory(data, terminal=True)
        used = [row for row in data['invocations'] if row['disposition'] == 'consumed']
        return ('configured' if used and all(row['assurance'] == 'configured'
                and configured_assurance(row.get('request'), policy) == 'configured' for row in used)
                else 'unknown')
    except (KeyError, TypeError, AttributeError, ValueError):
        return 'unknown'


def marker_assurance(data: dict, policy: dict | None = None, *, evidence: dict | None = None,
                     allowlist: dict | None = None, host_adapter=None) -> str:
    """The only source of the terminal marker's `ModelAssurance`: `verified` only when
    `reconcile_evidence` proves it, else `assurance_state`. Row `assurance` labels are never
    an input to `verified`; without a host adapter (the portable default) this is never verified.
    Total: both callees return `unknown` on any malformed input, so this never raises."""
    if reconcile_evidence(data, evidence, allowlist, policy, host_adapter=host_adapter) == 'verified':
        return 'verified'
    return assurance_state(data, policy)


def action_allowed(requirement: str, marker: dict, inventory_path: Path, digest: str,
                   current_final_hash: str, evidence: dict | None = None,
                   allowlist: dict | None = None, policy: dict | None = None,
                   host_adapter=None, expected_gated=None) -> bool:
    """Caller predicate: opt-in needs reconciled host evidence; portable default blocks.

    `expected_gated` (required for `qg-verified`) is the caller's own list of paths this action
    authorizes (design/plan: the path from the phase sub-skill's linted receipt or the orchestrator's
    in-context output, never re-read from the ledger; code: `git -C <root> diff --no-renames --no-relative --name-only -z
    <base>..HEAD` split on NUL, dropping empty entries: `-z` output ends with a NUL); it must be a non-empty list/tuple/set of strings, each in the inventory's
    `gated.paths`, so a genuine tuple for some other artifact cannot authorize this one.

    `digest`, `current_final_hash` and the marker's `FinalArtifactHash` must all be hex64; a
    missing one (for example after a `gated_hash` failure) returns False."""
    if requirement == 'none':
        return marker.get('Verdict') == 'PASS'
    if requirement != 'qg-verified' or marker.get('Verdict') != 'PASS':
        return False
    # Every binding input must be a real digest: a None/absent value never matches a None/absent value,
    # and a None final hash would otherwise silently turn the terminal read into a provisional one.
    if not (_hex64(current_final_hash) and _hex64(digest) and _hex64(marker.get('FinalArtifactHash'))):
        return False
    if (not isinstance(expected_gated, (list, tuple, set, frozenset))
            or any(not isinstance(item, str) for item in expected_gated)):
        return False
    expected_gated = {item for item in expected_gated if item}  # the trailing NUL of `-z` yields one ''
    if not expected_gated:
        return False
    if marker.get('MarkerFinality') != 'final-integration' or marker.get('FinalArtifactHash') != current_final_hash:
        return False
    if marker.get('ModelAssuranceInventory') != f'{inventory_path} sha256:{digest}':
        return False
    try:
        data = read_inventory(inventory_path, digest, marker['RunID'], marker['ArtifactHash'], current_final_hash)
    except (KeyError, ValueError):
        return False
    # The gated set must be the set the marker declares: it is otherwise self-certifying.
    try:
        declared = marker['Gated-Files']
        declared = set(json.loads(declared) if isinstance(declared, str) else declared)
    except (KeyError, TypeError, ValueError):
        return False
    if declared != set(data['gated']['paths']) - set(data['gated']['deleted']):
        return False
    # The tuple must belong to what this caller is authorizing, not merely be self-consistent.
    if not set(expected_gated) <= set(data['gated']['paths']):
        return False
    # A PASS marker needs a roster whose every chunk ended PASS (the roster is a terminal-schema field).
    if any(value != 'PASS' for value in data['roster']['terminal'].values()):
        return False
    # Digest and inventory claims cannot attest their own protected origin.
    return (marker.get('ModelAssurance') == 'verified'
            and reconcile_evidence(data, evidence or {}, allowlist or {}, policy or {},
                                   host_adapter=host_adapter) == 'verified')


def configured_assurance(request: dict | None, policy: dict | None) -> str:
    """A matched selector is configured, never independent execution proof."""
    if not request or not policy or not isinstance(request, dict) or not isinstance(policy, dict):
        return 'unknown'
    model = request.get('model')
    approved = policy.get(model) if isinstance(model, str) else None
    # A missing key never matches a missing key: effort and route must be observed non-empty strings on both sides.
    return ('configured' if isinstance(approved, dict)
            and all(isinstance(request.get(key), str) and request[key] and request[key] == approved.get(key)
                    for key in ('effort', 'route')) else 'unknown')


_PROC_STATUS = '/proc/self/status'


def _unprivileged_reviewer() -> bool:
    """Positive invariant: True only when this process provably cannot write a file it does not own.

    Real and effective uid non-zero, `/proc/self/status` readable (Linux), `CapEff`, `CapPrm` and
    `CapAmb` all zero, and `NoNewPrivs: 1` (no setuid/sudo escalation). Anything else, including an
    unreadable status file or a non-Linux host, is False so `reconcile_evidence` fails closed.
    The predicate measures the verifying process only: a host adapter must run reviewer children
    under the same or stricter constraints and attest that as part of its allowlisted contract
    (a contract requirement, not something this module checks).
    """
    if os.getuid() == 0 or os.geteuid() == 0:
        return False
    try:
        with open(_PROC_STATUS, encoding='ascii') as status:
            fields = dict(line.split(':', 1) for line in status if ':' in line)
        caps = [int(fields[key].split()[0], 16) for key in ('CapEff', 'CapPrm', 'CapAmb')]
        return not any(caps) and fields['NoNewPrivs'].split()[0] == '1'
    except (OSError, ValueError, IndexError, KeyError):
        return False


def _read_protected(path, owners, parent_checked: dict) -> bytes:
    """Open once without following symlinks; the file must be a non-group/other-writable
    regular file owned by one of the adapter's `owners` (uids other than the reviewer's).
    Ownership only keeps files out of an unprivileged reviewer's reach: any privileged
    reviewer can write them anyway, so `reconcile_evidence` returns `unknown` unless
    `_unprivileged_reviewer()` holds."""
    path = Path(path)
    parent = path.parent
    if parent not in parent_checked:
        # os.lstat, not Path.lstat: Path.lstat bypasses attribute-patched os.lstat on
        # Python <=3.13, silently vacuating the owner-check tests there (CI runs 3.12).
        info = os.lstat(parent)
        parent_checked[parent] = (not stat.S_ISLNK(info.st_mode) and not info.st_mode & 0o022
                                  and info.st_uid in owners)
    if not parent_checked[parent]:
        raise ValueError('unprotected evidence directory')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o022 or info.st_uid not in owners:
            raise ValueError('unprotected evidence file')
        raw = handle.read(MAX_INVENTORY_BYTES + 1)
    if len(raw) > MAX_INVENTORY_BYTES:
        raise ValueError('evidence file exceeds byte limit')
    return raw


def caller_allowed(requirement: str | None, marker: dict, inventory_path, digest: str | None,
                   current_final_hash: str | None, expected_gated=None,
                   evidence: dict | None = None, allowlist: dict | None = None,
                   policy: dict | None = None, host_adapter=None) -> bool:
    """Persisted opt-in predicate at phase/push/recovery boundaries.

    A missing or `none` requirement keeps legacy behavior and never engages the
    proof tuple; `Status: PASS` stays artifact closure and is never rewritten.
    Unsupported values — including `warden-verified`, whose Warden-wide proof
    contract does not exist — fail closed and block only the opted-in action.
    For `qg-verified`, `digest` and `current_final_hash` of `None` block the action: a
    `gated_hash` failure is never passed on as `None` (it blocks only the opted-in action).
    `expected_gated` is mandatory for `qg-verified` (absent/None/empty/mismatch -> False; see
    `action_allowed`). There is no `expected_run_id`: the marker's `RunID` is bound to the inventory
    and `expected_gated` binds the tuple to the caller's artifact, so a run id from the same ledger adds nothing.
    `evidence`, `allowlist`, `policy` and `host_adapter` come from the host adapter's
    own protected store, never from the ledger or the reviewer.
    """
    if requirement in (None, '', 'none'):
        return True
    if requirement != 'qg-verified':
        return False
    try:
        return action_allowed('qg-verified', marker, inventory_path, digest, current_final_hash,
                              evidence=evidence, allowlist=allowlist, policy=policy,
                              host_adapter=host_adapter, expected_gated=expected_gated)
    except (KeyError, TypeError, ValueError, OSError):
        return False


def reconcile_evidence(data: dict, evidence: dict | None, allowlist: dict | None, policy: dict | None,
                       *, host_adapter=None) -> str:
    """Reconcile host-owned evidence against the inventory; anything unproven is unknown.

    `verified` requires an injected host adapter (`.name`, `.version`, `.owner_uids`,
    `.authenticate(origin, canonical) -> bool`) that is on the human-approved allowlist
    and authenticates origin out of the reviewer's reach; evidence files owned by one of
    the adapter's uids and not child-writable; per-row attestation digests pinned by the
    inventory (hence by the marker's inventory digest); and one exact-ID
    model/effort/route request per consumed row that the policy approves and that every observed
    turn equals (so mixed, rewritten or effort-unobserved turns are never verified), and no consensus row (a roster
    with consensus membership, or a consumed row or journal line whose `kind` starts `consensus`, is
    capped at `unknown` until the consensus API exposes stable member identity). With no adapter (the portable
    default) this is always `unknown`: a key a same-uid child can read authenticates nothing.
    """
    try:
        if host_adapter is None:
            return 'unknown'
        _validate_inventory(data, terminal=True)
        # Consensus cap (design): the consensus API exposes no stable per-member identity or
        # source, so a run consuming any consensus row is never verified.
        if data['roster']['consensus'] or any(str(row.get('kind', '')).startswith('consensus')
                                              for row in data['invocations'] if row['disposition'] == 'consumed'):
            return 'unknown'
        approved = allowlist[host_adapter.name]
        if approved['version'] != host_adapter.version:
            return 'unknown'
        owners = frozenset(host_adapter.owner_uids)
        if not owners or {os.getuid(), os.geteuid()} & owners or not _unprivileged_reviewer():
            return 'unknown'  # evidence the reviewer's own uid owns, or a not-provably-unprivileged reviewer can write, is reviewer-writable
        records = evidence['records']
        checked: dict = {}
        if evidence['run_id'] != data['run_id']:
            return 'unknown'
        journal_raw = _read_protected(evidence['journal_path'], owners, checked)
        lines = [json.loads(line) for line in journal_raw.decode().splitlines() if line.strip()]
        if len(lines) > MAX_INVOCATIONS:
            return 'unknown'
        canonical = canonical_evidence(data, lines, records)
        try:
            authenticated = host_adapter.authenticate(evidence['origin'], canonical) is True
        except Exception:  # noqa: BLE001 - any adapter error downgrades, never escapes
            return 'unknown'
        if not authenticated:
            return 'unknown'
        consumed, seen, results = set(), set(), {}
        for line in lines:
            if line.get('disposition') == 'consumed' and str(line.get('kind', '')).startswith('consensus'):
                return 'unknown'  # the adapter's own journal observed a consensus call
            if line['run_id'] != data['run_id'] or line['id'] in seen:
                return 'unknown'  # wrong binding, or a bridged response counted twice
            seen.add(line['id'])
            if line.get('replay') or line.get('rollback'):
                return 'unknown'  # the design defines no replay/rollback semantics: never let one stand in for a consumed original
            if line['disposition'] not in ('consumed', 'unused'):
                return 'unknown'
            if line['disposition'] == 'consumed':
                consumed.add(line['id'])
                results[line['id']] = line['result_digest']
        expected = {row['id'] for row in data['invocations'] if row['disposition'] == 'consumed'}
        if consumed != expected or set(records) != consumed:
            return 'unknown'
        for row in data['invocations']:
            if row['disposition'] != 'consumed':
                continue
            raw = _read_protected(records[row['id']]['path'], owners, checked)
            digest = hashlib.sha256(raw).hexdigest()
            attestation = row.get('attestation') or {}
            if digest != records[row['id']]['digest'] or digest != attestation.get('digest') \
                    or attestation.get('result_digest') != results[row['id']]:
                return 'unknown'  # evidence must be the exact bytes the inventory pins
            record = json.loads(raw)
            request = row.get('request')
            if not isinstance(request, dict) or not all(isinstance(request.get(key), str) and request[key]
                                                         for key in ('model', 'effort', 'route')):
                return 'unknown'  # the dispatch's own request is the reference every turn must equal
            if (record['id'] != row['id'] or record['result_digest'] != results[row['id']]
                    or not record['turns'] or configured_assurance(request, policy) != 'configured'
                    or any(not isinstance(turn, dict) or any(turn.get(key) != request[key] for key in ('model', 'effort', 'route'))
                           for turn in record['turns'])):
                return 'unknown'
        return 'verified'
    except (KeyError, TypeError, ValueError, OSError, AttributeError, RecursionError, json.JSONDecodeError):
        return 'unknown'


def canonical_evidence(data: dict, journal: list, records: dict) -> bytes:
    """Bytes the host adapter authenticates: bound to the run, the accepted final artifact, the gated
    path set (paths, deletions, mode) and the terminal roster, so a rewritten inventory cannot re-point a
    genuine run at a different artifact or verdict."""
    return json.dumps({'run_id': data['run_id'], 'artifact_hash': data['artifact_hash'],
                       'final_artifact_hash': data['final_artifact_hash'],
                       'gated': data['gated'],
                       'roster': data['roster'],
                       'journal': journal, 'records': records},
                      sort_keys=True, separators=(',', ':')).encode()
