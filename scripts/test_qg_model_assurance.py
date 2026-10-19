#!/usr/bin/env python3
"""Portable QG artifact identity and no-adapter assurance checks."""
import hashlib
import hmac
from unittest import mock
import json
import os
from pathlib import Path
import stat
import struct
import subprocess
import tempfile
import unittest

import qg_model_assurance as qma
from qg_model_assurance import (artifact_hash, configured_assurance, write_inventory, read_inventory, assurance_state,
                                action_allowed, reconcile_evidence, caller_allowed, canonical_evidence, gated_hash,
                                marker_assurance)


def reference_hash(root, entries):
    common = Path(subprocess.check_output(['git', '-C', str(root), 'rev-parse', '--git-common-dir'], text=True).strip())
    if not common.is_absolute():
        common = root / common
    fields = ['crucible-qg-manifest-v1', str(common.resolve()), str(root.resolve()), str(len(entries))]
    for entry in sorted(entries, key=lambda e: e[0].encode()):
        fields.extend(entry)
    raw = b''.join(struct.pack('>Q', len(s.encode())) + s.encode() for s in fields)
    return hashlib.sha256(raw).hexdigest()


class ArtifactHashTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        subprocess.run(['git', '-C', str(self.root), 'init', '-q'], check=True)
        (self.root / 'a.txt').write_bytes(b'hello\n')
        (self.root / 'run').write_bytes(b'#!/bin/sh\n')
        (self.root / 'run').chmod(0o755)
        (self.root / 'link').symlink_to('a.txt')

    def test_canonical_manifest_and_changed_bytes(self):
        paths = ['run', 'link', 'gone', 'a.txt']
        entries = [
            ('a.txt', 'regular', '100644', hashlib.sha256(b'hello\n').hexdigest()),
            ('gone', 'deleted', '-', hashlib.sha256(b'').hexdigest()),
            ('link', 'symlink', '120000', hashlib.sha256(b'a.txt').hexdigest()),
            ('run', 'regular', '100755', hashlib.sha256(b'#!/bin/sh\n').hexdigest()),
        ]
        expected = reference_hash(self.root, entries)
        self.assertEqual(artifact_hash(self.root, paths, deleted={'gone'}), expected)
        self.assertEqual(artifact_hash(self.root, reversed(paths), deleted={'gone'}), expected)
        (self.root / 'a.txt').write_bytes(b'changed')
        self.assertNotEqual(artifact_hash(self.root, paths, deleted={'gone'}), expected)
        self.assertNotEqual(artifact_hash(self.root, ['a.txt'], document=True), expected)

    def test_document_raw_bytes(self):
        self.assertEqual(artifact_hash(self.root, ['a.txt'], document=True), hashlib.sha256(b'hello\n').hexdigest())

    def test_document_outside_git_and_non_git_set_fail_totally(self):
        with tempfile.TemporaryDirectory() as plain:
            Path(plain, 'doc.md').write_bytes(b'doc')
            self.assertEqual(artifact_hash(plain, ['doc.md'], document=True), hashlib.sha256(b'doc').hexdigest())
            with self.assertRaises(ValueError):  # git failure is a ValueError, not CalledProcessError
                artifact_hash(plain, ['doc.md'])
            with self.assertRaises(ValueError):
                artifact_hash(plain, ['nope.md'], document=True)

    def test_document_symlinked_parent_rejected(self):
        with tempfile.TemporaryDirectory() as real:
            Path(real, 'doc.md').write_bytes(b'doc')
            (self.root / 'dirlink').symlink_to(real, target_is_directory=True)
            with self.assertRaises(ValueError):
                artifact_hash(self.root, ['dirlink/doc.md'], document=True)

    def test_tombstone_under_deleted_directory(self):
        (self.root / 'keep.txt').write_text('k')
        self.assertEqual(len(artifact_hash(self.root, ['keep.txt', 'old/a.md'], deleted={'old/a.md'})), 64)
        with self.assertRaises(ValueError):  # a non-tombstone under a missing directory still fails closed
            artifact_hash(self.root, ['keep.txt', 'old/a.md'])

    def test_reject_invalid_set(self):
        for paths, deleted in [(['a.txt', 'a.txt'], set()), (['/a.txt'], set()), (['./a.txt'], set()),
                               (['../a.txt'], set()), (['a\x00.txt'], set()), (['missing'], set()),
                               (['a.txt'], {'missing'}), (['a.txt'], {'a.txt'})]:
            with self.subTest(paths=paths, deleted=deleted), self.assertRaises(ValueError):
                artifact_hash(self.root, paths, deleted=deleted)
        os.mkfifo(self.root / 'pipe')
        with self.assertRaises(ValueError):
            artifact_hash(self.root, ['pipe'])

    def test_identity_and_mode_bound(self):
        initial = artifact_hash(self.root, ['run'])
        (self.root / 'run').chmod(0o644)
        self.assertNotEqual(artifact_hash(self.root, ['run']), initial)
        with tempfile.TemporaryDirectory() as other:
            subprocess.run(['git', '-C', other, 'init', '-q'], check=True)
            Path(other, 'run').write_bytes(b'#!/bin/sh\n')
            Path(other, 'run').chmod(0o755)
            self.assertNotEqual(artifact_hash(Path(other), ['run']), initial)

    def test_exec_bit_is_owner_only_like_git(self):
        (self.root / 'run').chmod(0o644)
        plain = artifact_hash(self.root, ['run'])
        (self.root / 'run').chmod(0o654)  # group-x only: git still records 100644
        self.assertEqual(artifact_hash(self.root, ['run']), plain)
        (self.root / 'run').chmod(0o744)
        self.assertNotEqual(artifact_hash(self.root, ['run']), plain)

    def test_symlink_to_outside_is_hashed_not_followed(self):
        (self.root / 'link').unlink()
        (self.root / 'link').symlink_to('../outside')
        self.assertIsInstance(artifact_hash(self.root, ['link']), str)
        with tempfile.TemporaryDirectory() as outside:
            Path(outside, 'secret').write_text('outside')
            (self.root / 'escape').symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError):
                artifact_hash(self.root, ['escape/secret'])

    def test_no_adapter_never_verified(self):
        self.assertEqual(configured_assurance(None, None), 'unknown')
        self.assertEqual(configured_assurance({'model': 'provider/model', 'effort': 'high'}, None), 'unknown')
        policy = {'provider/model': {'effort': 'high', 'route': 'fixed'}}
        self.assertEqual(configured_assurance({'model': 'provider/model', 'effort': 'high', 'route': 'fixed'}, policy), 'configured')
        self.assertEqual(configured_assurance({'model': 'provider/model', 'effort': 'low', 'route': 'fixed'}, policy), 'unknown')
        self.assertEqual(configured_assurance({'model': 'provider/model', 'effort': 'high', 'route': 'other'}, policy), 'unknown')


GATED = {'paths': ['a.txt', 'gone'], 'deleted': ['gone'], 'mode': 'manifest'}


class InventoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name, 'run.json')
        self.data = {
            'version': 1, 'run_id': 'run-1', 'artifact_hash': 'a' * 64,
            'final_artifact_hash': 'b' * 64, 'gated': GATED,
            'roster': {'kind': 'single-artifact', 'chunks': ['artifact'], 'terminal': {'artifact': 'PASS'}, 'consensus': []},
            'invocations': [{'id': 'round-1-review', 'parent': 'run-1', 'scope': 'artifact/round-1',
                             'disposition': 'consumed', 'assurance': 'unknown', 'kind': 'review'}],
        }

    def test_write_readback_and_absent_host_evidence(self):
        digest = write_inventory(self.path, self.data, terminal=True)
        self.assertEqual(read_inventory(self.path, digest, 'run-1', 'a' * 64, 'b' * 64), self.data)
        self.assertEqual(assurance_state(self.data), 'unknown')
        self.data['invocations'][0]['assurance'] = 'configured'
        self.assertEqual(assurance_state(self.data), 'unknown')
        self.data['invocations'][0]['request'] = {'model': 'provider/model', 'effort': 'high', 'route': 'fixed'}
        policy = {'provider/model': {'effort': 'high', 'route': 'fixed'}}
        self.assertEqual(assurance_state(self.data, policy), 'configured')
        self.data['invocations'][0]['assurance'] = 'verified'
        self.assertEqual(assurance_state(self.data, policy), 'unknown')

    def test_marker_assurance_ignores_row_labels(self):
        # Rows self-labelled verified with hex attestations and no host adapter: never verified.
        row = self.data['invocations'][0]
        row.update(assurance='verified', attestation={'digest': 'c' * 64, 'result_digest': 'd' * 64})
        self.assertEqual(marker_assurance(self.data), 'unknown')
        row.update(assurance='configured', request={'model': 'provider/model', 'effort': 'high', 'route': 'fixed'})
        policy = {'provider/model': {'effort': 'high', 'route': 'fixed'}}
        self.assertEqual(marker_assurance(self.data, policy), 'configured')

    def test_malformed_request_or_policy_is_unknown_never_raises(self):
        row = self.data['invocations'][0]
        good = {'model': 'provider/model', 'effort': 'high', 'route': 'fixed'}
        policy = {'provider/model': {'effort': 'high', 'route': 'fixed'}}
        row.update(assurance='configured', request=good)
        self.assertEqual(marker_assurance(self.data, policy), 'configured')  # documented shape + policy
        for bad_policy in (['provider/model'], 'provider/model', 7):
            self.assertEqual(marker_assurance(self.data, bad_policy), 'unknown')
            self.assertEqual(assurance_state(self.data, bad_policy), 'unknown')
        self.assertEqual(marker_assurance(self.data, {'provider/model': 'high'}), 'unknown')
        for bad in ('provider/model', {'model': ['provider/model']}, {'model': 'provider/model', 'effort': 5},
                    ['provider/model']):
            row['request'] = bad
            self.assertEqual(marker_assurance(self.data, policy), 'unknown')
            with self.assertRaises(ValueError):  # the terminal schema refuses the shape outright
                write_inventory(self.path, self.data, terminal=True)
        self.assertEqual(assurance_state({'invocations': 'x'}, policy), 'unknown')  # total over a non-inventory
        self.assertEqual(marker_assurance(None, policy), 'unknown')

    def test_provisional_midrun_write_and_digestless_recovery_read(self):
        # Truthful incremental write: one of two chunks terminal, final hash and gated set not yet frozen.
        data = {**self.data, 'final_artifact_hash': None, 'gated': None,
                'roster': {'kind': 'chunked', 'chunks': ['c1', 'c2'], 'terminal': {'c1': 'PASS'}, 'consensus': ['synthesis']}}
        data['invocations'] = data['invocations'] + [
            {'id': 'synthesis', 'parent': 'run-1', 'scope': 'cross-chunk', 'disposition': 'unused', 'assurance': 'unknown'}]
        digest = write_inventory(self.path, data)
        self.assertEqual(read_inventory(self.path, None, 'run-1', 'a' * 64, None), data)  # provisional recovery read
        self.assertEqual(read_inventory(self.path, digest, 'run-1', 'a' * 64, None), data)
        for bad in (lambda: write_inventory(self.path, data, terminal=True),
                    lambda: read_inventory(self.path, digest, 'run-1', 'a' * 64, 'b' * 64),
                    lambda: read_inventory(self.path, None, 'run-1', 'a' * 64, 'b' * 64)):
            with self.assertRaises(ValueError):
                bad()
        self.assertEqual(assurance_state(data), 'unknown')  # a provisional inventory never reads as assured

    def test_terminal_schema_checks_status_values_and_consensus_consumed(self):
        from copy import deepcopy
        for label, mutate in {
            'unfinished status': lambda d: d['roster']['terminal'].update(artifact='IN_PROGRESS'),
            'terminal not a dict': lambda d: d['roster'].update(terminal=['artifact']),
            'consensus unused': lambda d: (d['roster'].update(consensus=['m']),
                                           d['invocations'].append({'id': 'm', 'parent': 'run-1', 'scope': 's',
                                                                    'disposition': 'unused', 'assurance': 'unknown'})),
            'consensus not a list': lambda d: d['roster'].update(consensus='1'),
            'no gated set': lambda d: d.update(gated=None),
            'deleted outside gated set': lambda d: d.update(gated={'paths': ['a'], 'deleted': ['b'], 'mode': 'manifest'}),
            'gated mode missing': lambda d: d.update(gated={'paths': ['a'], 'deleted': []}),
            'gated mode unknown': lambda d: d.update(gated={**GATED, 'mode': 'raw'}),
            'document mode with two paths': lambda d: d.update(gated={**GATED, 'mode': 'document'}),
            'document mode with deletion': lambda d: d.update(gated={'paths': ['a'], 'deleted': ['a'], 'mode': 'document'}),
            'row kind not a string': lambda d: d['invocations'][0].update(kind=7),
            'row kind missing': lambda d: d['invocations'][0].pop('kind'),
            'row kind empty': lambda d: d['invocations'][0].update(kind=''),
            'verified row lacks attestation': lambda d: d['invocations'][0].update(assurance='verified', attestation={}),
        }.items():
            data = deepcopy(self.data)
            mutate(data)
            with self.subTest(label), self.assertRaises(ValueError):
                write_inventory(self.path, data, terminal=True)

    def test_gated_hash_recomputes_from_persisted_set(self):
        root = Path(self.tmp.name, 'repo')
        root.mkdir()
        subprocess.run(['git', '-C', str(root), 'init', '-q'], check=True)
        (root / 'a.txt').write_text('x')
        expected = artifact_hash(root, ['a.txt', 'gone'], deleted={'gone'})
        self.assertEqual(gated_hash(self.data, root), expected)
        (root / 'a.txt').write_text('y')  # working tree diverges from the gated bytes
        self.assertNotEqual(gated_hash(self.data, root), expected)

    def test_gated_hash_mode_comes_from_persisted_data(self):
        root = Path(self.tmp.name, 'plain')
        root.mkdir()
        (root / 'doc.md').write_bytes(b'doc')
        data = {**self.data, 'gated': {'paths': ['doc.md'], 'deleted': [], 'mode': 'document'}}
        self.assertEqual(gated_hash(data, root), hashlib.sha256(b'doc').hexdigest())  # no git, no mode argument
        subprocess.run(['git', '-C', str(root), 'init', '-q'], check=True)
        manifest = {**data, 'gated': {**data['gated'], 'mode': 'manifest'}}
        self.assertNotEqual(gated_hash(manifest, root), gated_hash(data, root))

    def test_read_inventory_size_cap_and_none_requires_pass(self):
        self.path.write_bytes(b' ' * (qma.MAX_INVENTORY_BYTES + 1))
        with self.assertRaises(ValueError):
            read_inventory(self.path, None, 'run-1', 'a' * 64, None)
        self.assertFalse(action_allowed('none', {'Verdict': 'ESCALATED'}, self.path, 'x', 'x'))

    def test_weakest_state_over_consumed_rows(self):
        policy = {'provider/model': {'effort': 'high', 'route': 'fixed'}}
        request = {'model': 'provider/model', 'effort': 'high', 'route': 'fixed'}
        self.data['invocations'] = [
            {'id': f'r{i}', 'parent': 'run-1', 'scope': 's', 'disposition': 'consumed',
             'assurance': 'configured', 'kind': 'review', 'request': dict(request)} for i in range(2)]
        self.assertEqual(assurance_state(self.data, policy), 'configured')
        self.data['invocations'][1]['assurance'] = 'unknown'  # one weaker row caps the run
        self.assertEqual(assurance_state(self.data, policy), 'unknown')
        self.data['invocations'][1]['assurance'] = 'configured'
        self.data['invocations'][1]['request']['route'] = 'other'
        self.assertEqual(assurance_state(self.data, policy), 'unknown')

    def test_tamper_and_binding_fail_closed(self):
        digest = write_inventory(self.path, self.data, terminal=True)
        for args in [(digest, 'other', 'a' * 64, 'b' * 64), (digest, 'run-1', 'c' * 64, 'b' * 64),
                     (digest, 'run-1', 'a' * 64, 'c' * 64), ('0' * 64, 'run-1', 'a' * 64, 'b' * 64)]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                read_inventory(self.path, *args)
        self.path.write_text('{}')
        with self.assertRaises(ValueError):
            read_inventory(self.path, digest, 'run-1', 'a' * 64, 'b' * 64)

    def test_opt_in_blocks_unknown_without_changing_artifact_pass(self):
        digest = write_inventory(self.path, self.data, terminal=True)
        marker = {'Verdict': 'PASS', 'MarkerFinality': 'final-integration', 'RunID': 'run-1',
                  'ArtifactHash': 'a' * 64, 'FinalArtifactHash': 'b' * 64,
                  'ModelAssurance': 'unknown', 'ModelAssuranceInventory': f'{self.path} sha256:{digest}'}
        self.assertTrue(action_allowed('none', marker, self.path, digest, 'b' * 64))
        self.assertFalse(action_allowed('qg-verified', marker, self.path, digest, 'b' * 64))
        self.assertFalse(action_allowed('warden-verified', marker, self.path, digest, 'b' * 64))
        self.assertFalse(action_allowed('qg-verified', {**marker, 'ModelAssurance': 'verified'}, self.path, digest, 'b' * 64))

    def test_incomplete_or_duplicate_inventory_rejected(self):
        from copy import deepcopy
        invalid = []
        for mutation in ('missing-chunk', 'duplicate-id', 'missing-parent', 'extra-consensus', 'bad-disposition'):
            data = deepcopy(self.data)
            if mutation == 'missing-chunk':
                data['roster']['terminal'] = {}
            elif mutation == 'duplicate-id':
                data['invocations'].append(deepcopy(data['invocations'][0]))
            elif mutation == 'missing-parent':
                data['invocations'][0]['parent'] = 'missing'
            elif mutation == 'extra-consensus':
                data['roster']['consensus'] = ['missing-member']
            else:
                data['invocations'][0]['disposition'] = 'not-a-status'
            invalid.append(data)
        for data in invalid:
            with self.subTest(data=data), self.assertRaises(ValueError):
                write_inventory(self.path, data, terminal=True)


class FakeAdapter:
    """Test double for the host adapter (#12). It owns its key in memory, never on a
    same-uid-readable path; real origin protection is the adapter's, not this module's."""
    name, version = 'test-host', '2'

    def __init__(self, owner_uids, key=b'adapter-private-key'):
        self.owner_uids, self.key = frozenset(owner_uids), key

    def sign(self, canonical):
        return hmac.new(self.key, canonical, hashlib.sha256).hexdigest()

    def authenticate(self, origin, canonical):
        return hmac.compare_digest(self.sign(canonical), origin['hmac'])


STATUS_OK = 'Name:\tx\nCapEff:\t0000000000000000\nCapPrm:\t0000000000000000\nCapAmb:\t0000000000000000\nNoNewPrivs:\t1\n'


class EvidenceFixture:
    """Shared host-evidence bundle starting from a verified configuration; each rejection
    test flips exactly one field. The reviewer's uid is patched so files owned by the real
    (adapter) uid are not reviewer-owned."""
    POLICY = {'provider/model': {'effort': 'high', 'route': 'fixed'}}
    TURN = {'model': 'provider/model', 'effort': 'high', 'route': 'fixed'}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name, 'evidence')
        self.dir.mkdir()
        self.dir.chmod(0o700)
        self.real_uid = os.getuid()
        self.adapter = FakeAdapter({self.real_uid})
        patcher = mock.patch.object(qma.os, 'getuid', return_value=self.real_uid + 1)
        patcher.start()
        self.addCleanup(patcher.stop)
        # Run identically under any uid or capability set: the reviewer is an unprivileged uid, no caps, NoNewPrivs 1.
        mock.patch.object(qma.os, 'geteuid', return_value=self.real_uid + 1).start()
        self.addCleanup(mock.patch.stopall)
        caps = Path(self.tmp.name, 'status')
        caps.write_text(STATUS_OK)
        mock.patch.object(qma, '_PROC_STATUS', str(caps)).start()
        self.data = {
            'version': 1, 'run_id': 'run-1', 'artifact_hash': 'a' * 64,
            'final_artifact_hash': 'b' * 64, 'gated': GATED,
            'roster': {'kind': 'chunked', 'chunks': ['c1', 'c2'], 'terminal': {'c1': 'PASS', 'c2': 'PASS'},
                       'consensus': []},
            'invocations': [
                {'id': 'review', 'parent': 'run-1', 'scope': 'c1', 'disposition': 'consumed', 'assurance': 'verified', 'kind': 'review', 'request': dict(self.TURN)},
                {'id': 'synthesis', 'parent': 'run-1', 'scope': 'c2', 'disposition': 'consumed', 'assurance': 'verified', 'kind': 'review', 'request': dict(self.TURN)},
                {'id': 'failed-member', 'parent': 'run-1', 'scope': 'c2', 'disposition': 'unused', 'assurance': 'unknown', 'kind': 'review'},
            ],
        }
        self.allowlist = {'test-host': {'version': '2'}}
        self.journal = [
            {'id': 'review', 'run_id': 'run-1', 'disposition': 'consumed', 'result_digest': '1' * 64},
            {'id': 'synthesis', 'run_id': 'run-1', 'disposition': 'consumed', 'result_digest': '2' * 64},
            {'id': 'failed-member', 'run_id': 'run-1', 'disposition': 'unused', 'result_digest': '3' * 64},
        ]
        self.records = {}
        for name, digest, turns in [('review', '1' * 64, 2), ('synthesis', '2' * 64, 1)]:
            self.put_record(name, {'id': name, 'result_digest': digest, 'turns': [self.TURN] * turns})
        self.evidence = self.signed()

    def put_record(self, name, record):
        path = self.dir / f'{name}.json'
        path.write_text(json.dumps(record))
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        self.records[name] = {'path': str(path), 'digest': digest}
        row = next(r for r in self.data['invocations'] if r['id'] == name)
        row['attestation'] = {'digest': digest, 'result_digest': record['result_digest']}

    def signed(self, key=None, journal=None, records=None):
        journal = self.journal if journal is None else journal
        records = self.records if records is None else records
        self.journal_path = self.dir / 'journal.jsonl'
        self.journal_path.write_text(''.join(json.dumps(line) + '\n' for line in journal))
        adapter = FakeAdapter(set(), key) if key else self.adapter
        return {'run_id': 'run-1', 'journal_path': str(self.journal_path), 'records': records,
                'origin': {'hmac': adapter.sign(canonical_evidence(self.data, journal, records))}}

    def reconcile(self, evidence=None, allowlist=None, policy=None, adapter='default'):
        return reconcile_evidence(self.data, evidence if evidence is not None else self.evidence,
                                  self.allowlist if allowlist is None else allowlist,
                                  self.POLICY if policy is None else policy,
                                  host_adapter=self.adapter if adapter == 'default' else adapter)


class EvidenceReconciliationTest(EvidenceFixture, unittest.TestCase):
    def test_complete_protected_evidence_verifies(self):
        self.assertEqual(self.reconcile(), 'verified')

    def test_production_default_fails_closed(self):
        self.assertEqual(self.reconcile(adapter=None), 'unknown')  # no host adapter: never verified
        self.assertEqual(reconcile_evidence(self.data, self.evidence, {}, self.POLICY, host_adapter=self.adapter), 'unknown')
        self.assertEqual(reconcile_evidence(self.data, {}, {}, {}), 'unknown')
        self.assertEqual(reconcile_evidence(self.data, None, None, None), 'unknown')
        self.assertEqual(self.reconcile(allowlist={'other-host': self.allowlist['test-host']}), 'unknown')
        self.assertEqual(self.reconcile(allowlist={'test-host': {'version': '3'}}), 'unknown')

    def test_same_uid_evidence_never_verifies(self):
        # The reviewer's real uid owns the files: a same-uid child could have forged them.
        with mock.patch.object(qma.os, 'getuid', return_value=self.real_uid):
            self.assertEqual(self.reconcile(), 'unknown')
        self.assertEqual(self.reconcile(adapter=FakeAdapter(set())), 'unknown')

    def test_privileged_reviewer_never_verifies(self):
        self.assertEqual(self.reconcile(), 'verified')
        for name in ('getuid', 'geteuid'):  # uid 0, real or effective, can rewrite any adapter-owned file
            with mock.patch.object(qma.os, name, return_value=0):
                self.assertEqual(self.reconcile(), 'unknown', name)
        with mock.patch.object(qma, '_unprivileged_reviewer', return_value=False):
            self.assertEqual(self.reconcile(), 'unknown')
        status = Path(self.tmp.name, 'cap-status')
        with mock.patch.object(qma.os, 'getuid', return_value=1), mock.patch.object(qma.os, 'geteuid', return_value=1), \
                mock.patch.object(qma, '_PROC_STATUS', str(status)):
            status.write_text(STATUS_OK)
            self.assertTrue(qma._unprivileged_reviewer())
            for label, text in (
                    ('CapEff', STATUS_OK.replace('CapEff:\t0000000000000000', 'CapEff:\t0000000000000002')),
                    ('CapEff non-DAC bit', STATUS_OK.replace('CapEff:\t0000000000000000', 'CapEff:\t0000000000200000')),
                    ('CapPrm', STATUS_OK.replace('CapPrm:\t0000000000000000', 'CapPrm:\t0000000000000001')),
                    ('CapAmb', STATUS_OK.replace('CapAmb:\t0000000000000000', 'CapAmb:\t0000000000000001')),
                    ('NoNewPrivs 0', STATUS_OK.replace('NoNewPrivs:\t1', 'NoNewPrivs:\t0')),
                    ('NoNewPrivs absent', STATUS_OK.replace('NoNewPrivs:\t1\n', '')),
                    ('CapAmb absent', STATUS_OK.replace('CapAmb:\t0000000000000000\n', ''))):
                status.write_text(text)
                self.assertFalse(qma._unprivileged_reviewer(), label)
                self.assertEqual(self.reconcile(), 'unknown', label)
            status.unlink()
            self.assertFalse(qma._unprivileged_reviewer())  # unreadable status fails closed
            self.assertEqual(self.reconcile(), 'unknown')

    def test_record_rewritten_after_signing(self):
        evidence = self.signed()
        record = {'id': 'review', 'result_digest': '1' * 64, 'turns': [self.TURN] * 5}
        path = Path(self.records['review']['path'])
        path.write_text(json.dumps(record))
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        self.records['review']['digest'] = digest  # the evidence's records map is the signed dict object
        self.data['invocations'][0]['attestation']['digest'] = digest
        # digests now agree everywhere except the signature, which covered the old record digest
        self.assertEqual(self.reconcile(evidence=evidence), 'unknown')
        self.assertEqual(self.reconcile(evidence=self.signed()), 'verified')  # re-signed: genuine

    def test_canonical_covers_every_top_level_field(self):
        base = canonical_evidence(self.data, self.journal, self.records)
        other = {**self.data}
        for key in ('run_id', 'artifact_hash', 'final_artifact_hash'):
            other[key] = 'f' * 64 if key != 'run_id' else 'run-2'
            self.assertNotEqual(canonical_evidence(other, self.journal, self.records), base, key)
            other[key] = self.data[key]
        self.assertNotEqual(canonical_evidence(self.data, self.journal[:-1], self.records), base, 'journal')
        for name in self.records:
            for field in ('digest', 'path'):
                changed = {**self.records, name: {**self.records[name], field: 'x' * 64}}
                self.assertNotEqual(canonical_evidence(self.data, self.journal, changed), base, f'{name}.{field}')
        self.assertNotEqual(canonical_evidence(self.data, self.journal, {}), base, 'records')

    def _foreign_owner(self, name):
        """Patch one stat call so only that check sees a uid outside the adapter's owners."""
        real = getattr(os, name)
        foreign = self.real_uid + 5

        def fake(target, *args, **kwargs):
            info = real(target, *args, **kwargs)
            wanted = (Path(str(target)) == self.dir) if name == 'lstat' else stat.S_ISREG(info.st_mode)
            if not wanted:
                return info
            return mock.Mock(st_mode=info.st_mode, st_uid=foreign)
        return mock.patch.object(qma.os, name, side_effect=fake)

    def test_owner_checks_each_reached_and_independent(self):
        self.assertEqual(self.reconcile(), 'verified')
        with self._foreign_owner('lstat'):  # directory owner only
            self.assertEqual(self.reconcile(), 'unknown')
        with self._foreign_owner('fstat'):  # file owner only
            self.assertEqual(self.reconcile(), 'unknown')
        # Reviewer uid distinct from the owner but the adapter does not own the files.
        with mock.patch.object(qma.os, 'getuid', return_value=self.real_uid + 2):
            self.assertEqual(self.reconcile(adapter=FakeAdapter({self.real_uid + 1})), 'unknown')

    def test_consensus_cap_is_code_enforced(self):
        self.assertEqual(self.reconcile(), 'verified')
        self.data['roster']['consensus'] = ['synthesis']  # mandatory consensus member, consumed
        self.assertEqual(self.reconcile(evidence=self.signed()), 'unknown')
        self.data['roster']['consensus'] = []
        self.data['invocations'][0]['kind'] = 'consensus-member'  # a consumed consensus row, single flip
        self.assertEqual(self.reconcile(evidence=self.signed()), 'unknown')
        self.data['invocations'][0]['kind'] = 'review'
        self.assertEqual(self.reconcile(evidence=self.signed()), 'verified')

    def test_authenticate_must_return_true(self):
        class Truthy(FakeAdapter):
            def authenticate(self, origin, canonical):
                return 'yes'
        self.assertEqual(self.reconcile(adapter=Truthy({self.real_uid})), 'unknown')

    def test_records_must_match_consumed_set_and_digests(self):
        extra = {**self.records, 'ghost': dict(self.records['review'])}
        self.assertEqual(self.reconcile(evidence=self.signed(records=extra)), 'unknown')
        wrong = {**self.records, 'review': {**self.records['review'], 'digest': 'f' * 64}}
        self.assertEqual(self.reconcile(evidence=self.signed(records=wrong)), 'unknown')

    def test_unauthenticated_or_child_writable_origin_unknown(self):
        self.assertEqual(self.reconcile(evidence={**self.evidence, 'origin': {'hmac': '0' * 64}}), 'unknown')
        self.assertEqual(self.reconcile(evidence=self.signed(key=b'forged-key')), 'unknown')
        self.journal_path.chmod(0o664)
        self.assertEqual(self.reconcile(), 'unknown')
        self.journal_path.chmod(0o600)
        self.assertEqual(self.reconcile(), 'verified')
        self.dir.chmod(0o775)
        self.assertEqual(self.reconcile(), 'unknown')

    def test_symlinked_journal_record_or_directory_unknown(self):
        real = self.dir / 'real.jsonl'
        self.journal_path.rename(real)
        self.journal_path.symlink_to(real)
        self.assertEqual(self.reconcile(), 'unknown')
        self.journal_path.unlink()
        real.rename(self.journal_path)
        self.assertEqual(self.reconcile(), 'verified')
        record = Path(self.records['review']['path'])
        moved = self.dir / 'moved.json'
        record.rename(moved)
        record.symlink_to(moved)
        self.assertEqual(self.reconcile(), 'unknown')
        record.unlink()
        moved.rename(record)
        link = Path(self.tmp.name, 'evidence-link')
        link.symlink_to(self.dir, target_is_directory=True)
        relocated = {**self.evidence, 'journal_path': str(link / 'journal.jsonl')}
        self.assertEqual(self.reconcile(evidence=relocated), 'unknown')

    def test_geteuid_owner_unknown(self):
        with mock.patch.object(qma.os, 'geteuid', return_value=self.real_uid):
            self.assertEqual(self.reconcile(), 'unknown')

    def test_all_unused_inventory_never_configured(self):
        for row in self.data['invocations']:
            row['disposition'] = 'unused'
        self.assertEqual(assurance_state(self.data, self.POLICY), 'unknown')

    def test_inventory_row_cap(self):
        rows = [{'id': f'r{i}', 'parent': 'run-1', 'scope': 'c1', 'disposition': 'unused', 'assurance': 'unknown', 'kind': 'review'}
                for i in range(qma.MAX_INVOCATIONS + 1)]
        with self.assertRaises(ValueError):
            qma._validate_inventory({**self.data, 'invocations': rows}, terminal=True)
        qma._validate_inventory({**self.data, 'invocations': rows[:-1]}, terminal=True)

    def test_journal_over_cap_unknown(self):
        flood = self.journal + [{'id': f'x{i}', 'run_id': 'run-1', 'disposition': 'unused', 'result_digest': '3' * 64}
                                for i in range(qma.MAX_INVOCATIONS)]
        self.assertEqual(self.reconcile(evidence=self.signed(journal=flood)), 'unknown')

    def test_turns_differing_from_approved_request_unknown(self):
        for turns in ([self.TURN, {**self.TURN, 'model': 'provider/other'}], [{**self.TURN, 'effort': 'low'}],
                      [{**self.TURN, 'route': 'other'}], []):
            self.put_record('review', {'id': 'review', 'result_digest': '1' * 64, 'turns': turns})
            self.assertEqual(self.reconcile(evidence=self.signed()), 'unknown')

    def test_request_policy_approval_required(self):
        # Request and every turn agree, so only the policy approval of the request can reject them.
        def case(request, policy=None):
            for row in self.data['invocations'][:2]:
                row['request'] = dict(request)
            for name, digest in (('review', '1' * 64), ('synthesis', '2' * 64)):
                self.put_record(name, {'id': name, 'result_digest': digest, 'turns': [request]})
            return self.reconcile(evidence=self.signed(), policy=policy)
        self.assertEqual(case(self.TURN), 'verified')  # baseline: approved ID at approved effort
        self.assertEqual(case({**self.TURN, 'model': 'provider/cheap-haiku'}), 'unknown')
        self.assertEqual(case({**self.TURN, 'effort': 'low'}), 'unknown')
        self.assertEqual(case(self.TURN, policy={}), 'unknown')
        for row in self.data['invocations'][:2]:
            row['request'] = dict(self.TURN)
        self.assertEqual(reconcile_evidence(self.data, self.evidence, self.allowlist, None, host_adapter=self.adapter), 'unknown')

    def _two_model_case(self, turns, request=None):
        policy = {**self.POLICY, 'provider/b': {'effort': 'xhigh', 'route': 'r2'}}
        other = {'model': 'provider/b', 'effort': 'xhigh', 'route': 'r2'}
        self.data['invocations'][0]['request'] = request or dict(self.TURN)
        self.put_record('review', {'id': 'review', 'result_digest': '1' * 64, 'turns': [t(other, self.TURN) for t in turns]})
        return self.reconcile(evidence=self.signed(), policy=policy)

    def test_mixed_approved_models_unknown(self):
        # Both IDs are approved by policy, but one invocation must not switch model/effort/route between turns.
        self.assertEqual(self._two_model_case([lambda o, b: b, lambda o, b: b]), 'verified')
        self.assertEqual(self._two_model_case([lambda o, b: b, lambda o, b: o]), 'unknown')

    def test_turns_contradict_request_unknown(self):
        # A silent substitution to another approved ID: turns are all approved but differ from the request.
        self.assertEqual(self._two_model_case([lambda o, b: o, lambda o, b: o]), 'unknown')
        self.assertEqual(self._two_model_case([lambda o, b: b], request={'model': 'provider/b', 'effort': 'xhigh', 'route': 'r2'}), 'unknown')
        row = self.data['invocations'][0]
        for bad in (None, 'provider/model', {'model': 'provider/model', 'effort': 'high'}, {**self.TURN, 'route': ''}):
            row['request'] = bad
            self.put_record('review', {'id': 'review', 'result_digest': '1' * 64, 'turns': [self.TURN]})
            self.assertEqual(self.reconcile(evidence=self.signed()), 'unknown', bad)
        row['request'] = dict(self.TURN)

    def test_effortless_turn_or_policy_unknown(self):
        bare = {'model': 'provider/model'}
        self.data['invocations'][0]['request'] = dict(bare)
        self.put_record('review', {'id': 'review', 'result_digest': '1' * 64, 'turns': [bare]})
        self.assertEqual(self.reconcile(evidence=self.signed(), policy={'provider/model': {}}), 'unknown')
        self.assertEqual(configured_assurance(bare, {'provider/model': {}}), 'unknown')
        self.assertEqual(configured_assurance({**self.TURN, 'effort': ''}, {'provider/model': {**self.TURN, 'effort': ''}}),
                         'unknown')
        self.data['invocations'][0]['request'] = dict(self.TURN)
        self.put_record('review', {'id': 'review', 'result_digest': '1' * 64, 'turns': [{'model': 'provider/model'}]})
        self.assertEqual(self.reconcile(evidence=self.signed()), 'unknown')  # turn observed no effort/route

    def test_adapter_error_and_bool_version_unknown(self):
        class Boom(FakeAdapter):
            def authenticate(self, origin, canonical):
                raise RuntimeError('adapter down')
        boom = Boom({self.real_uid})
        self.assertEqual(self.reconcile(adapter=boom), 'unknown')
        self.assertEqual(marker_assurance(self.data, self.POLICY, evidence=self.evidence, allowlist=self.allowlist,
                                          host_adapter=boom), 'unknown')
        self.data['version'] = True
        self.assertEqual(self.reconcile(), 'unknown')

    def test_evidence_file_size_cap(self):
        path = self.dir / 'journal.jsonl'
        path.write_text(path.read_text() + ' ' * qma.MAX_INVENTORY_BYTES)
        with self.assertRaises(ValueError):
            qma._read_protected(path, frozenset({self.real_uid}), {})

    def test_injected_duplicate_or_replayed_journal(self):
        injected = self.journal + [{'id': 'ghost', 'run_id': 'run-1', 'disposition': 'consumed', 'result_digest': '4' * 64}]
        self.assertEqual(self.reconcile(evidence=self.signed(journal=injected)), 'unknown')
        duplicated = self.journal + [dict(self.journal[0])]
        self.assertEqual(self.reconcile(evidence=self.signed(journal=duplicated)), 'unknown')
        replayed = [dict(line, replay=True) if line['id'] == 'synthesis' else line for line in self.journal]
        self.assertEqual(self.reconcile(evidence=self.signed(journal=replayed)), 'unknown')

    def test_extra_consumed_invocation_not_in_inventory(self):
        # The journal AND the records carry a consumed `ghost` the inventory omits: completeness fails.
        ghost = {'id': 'ghost', 'run_id': 'run-1', 'disposition': 'consumed', 'result_digest': '4' * 64}
        path = self.dir / 'ghost.json'
        path.write_text(json.dumps({'id': 'ghost', 'result_digest': '4' * 64, 'turns': [self.TURN]}))
        records = {**self.records, 'ghost': {'path': str(path), 'digest': hashlib.sha256(path.read_bytes()).hexdigest()}}
        self.assertEqual(self.reconcile(evidence=self.signed(journal=self.journal + [ghost], records=records)), 'unknown')

    def test_journal_edited_after_signing(self):
        evidence = self.signed()
        # an unused line is checked by nothing else, so only the signature can notice the edit
        edited = [dict(line, result_digest='9' * 64) if line['id'] == 'failed-member' else line for line in self.journal]
        self.journal_path.write_text(''.join(json.dumps(line) + '\n' for line in edited))
        self.assertEqual(self.reconcile(evidence=evidence), 'unknown')  # signature no longer covers the bytes

    def test_record_self_mismatch_and_unknown_disposition(self):
        self.put_record('review', {'id': 'other', 'result_digest': '1' * 64, 'turns': [self.TURN]})
        self.assertEqual(self.reconcile(evidence=self.signed()), 'unknown')  # record names another invocation
        self.put_record('review', {'id': 'review', 'result_digest': '8' * 64, 'turns': [self.TURN]})
        self.data['invocations'][0]['attestation']['result_digest'] = '1' * 64
        self.assertEqual(self.reconcile(evidence=self.signed()), 'unknown')  # record digest != journal result
        self.put_record('review', {'id': 'review', 'result_digest': '1' * 64, 'turns': [self.TURN] * 2})
        self.assertEqual(self.reconcile(evidence=self.signed()), 'verified')
        odd = [dict(line, disposition='pending') if line['id'] == 'failed-member' else line for line in self.journal]
        self.assertEqual(self.reconcile(evidence=self.signed(journal=odd)), 'unknown')

    def test_review_mode_consensus_row_without_kind_or_roster_entry(self):
        # Periodic review-mode consensus is not in roster.consensus: the required `kind` carries the cap.
        self.data['invocations'][0].pop('kind')
        with self.assertRaises(ValueError):
            write_inventory(Path(self.tmp.name, 'x.json'), self.data, terminal=True)
        self.assertEqual(self.reconcile(evidence=self.signed()), 'unknown')  # terminal schema rejects it
        self.data['invocations'][0]['kind'] = 'consensus-synthesis'
        self.assertEqual(self.reconcile(evidence=self.signed()), 'unknown')
        self.data['invocations'][0]['kind'] = 'review'
        flagged = [dict(line, kind='consensus-member') if line['id'] == 'review' else line for line in self.journal]
        self.assertEqual(self.reconcile(evidence=self.signed(journal=flagged)), 'unknown')  # journal-observed

    def test_marker_assurance_verified_only_via_reconcile(self):
        self.assertEqual(marker_assurance(self.data, self.POLICY), 'unknown')  # labels alone, no adapter
        self.assertEqual(marker_assurance(self.data, self.POLICY, evidence=self.evidence,
                                          allowlist=self.allowlist, host_adapter=self.adapter), 'verified')
        self.assertEqual(marker_assurance(self.data, self.POLICY, evidence=self.evidence,
                                          allowlist={}, host_adapter=self.adapter), 'unknown')

    def test_missing_stale_or_unavailable_records(self):
        stale = self.signed()
        Path(self.records['review']['path']).write_text('{"tampered": true}')
        self.assertEqual(self.reconcile(evidence=stale), 'unknown')
        os.unlink(self.records['review']['path'])
        self.assertEqual(self.reconcile(), 'unknown')
        self.put_record('review', {'id': 'review', 'result_digest': '1' * 64, 'turns': [self.TURN]})
        self.assertEqual(self.reconcile(evidence=self.signed()), 'verified')
        os.unlink(self.journal_path)
        self.assertEqual(self.reconcile(), 'unknown')
        self.journal_path.write_text('not-json\n')
        self.assertEqual(self.reconcile(), 'unknown')

    def test_wrong_run_or_dispatch_binding(self):
        self.assertEqual(self.reconcile(evidence={**self.evidence, 'run_id': 'run-2'}), 'unknown')
        rebound = [dict(line, run_id='run-2') if line['id'] == 'review' else line for line in self.journal]
        self.assertEqual(self.reconcile(evidence=self.signed(journal=rebound)), 'unknown')
        self.put_record('review', {'id': 'other-invocation', 'result_digest': '1' * 64, 'turns': [self.TURN]})
        self.assertEqual(self.reconcile(evidence=self.signed()), 'unknown')

    def test_evidence_must_match_inventory_attestation(self):
        # Authentic, internally consistent evidence for a different result than the inventory pinned.
        self.data['invocations'][0]['attestation']['digest'] = 'e' * 64
        self.assertEqual(self.reconcile(evidence=self.signed()), 'unknown')
        self.data['invocations'][0]['attestation']['digest'] = self.records['review']['digest']
        self.data['invocations'][0]['attestation']['result_digest'] = 'e' * 64
        self.assertEqual(self.reconcile(evidence=self.signed()), 'unknown')

    def test_evidence_signed_for_other_final_artifact_unknown(self):
        other = self.signed()
        self.data['final_artifact_hash'] = 'c' * 64
        self.assertEqual(self.reconcile(evidence=other), 'unknown')

    def test_look_harder_demotion_and_consensus_membership(self):
        self.data['invocations'].append({'id': 'look-harder', 'parent': 'run-1', 'scope': 'c1',
                                         'disposition': 'consumed', 'assurance': 'verified', 'kind': 'review',
                                         'request': dict(self.TURN)})
        self.journal.append({'id': 'look-harder', 'run_id': 'run-1', 'disposition': 'consumed', 'result_digest': '5' * 64})
        self.put_record('look-harder', {'id': 'look-harder', 'result_digest': '5' * 64, 'turns': [self.TURN]})
        self.assertEqual(self.reconcile(evidence=self.signed()), 'verified')
        demoted = [dict(line, disposition='unused') if line['id'] == 'synthesis' else line
                   for line in self.journal]
        self.assertEqual(self.reconcile(evidence=self.signed(journal=demoted)), 'unknown')

    def test_consensus_member_unused_in_inventory_unknown(self):
        self.data['roster']['consensus'] = ['synthesis']
        self.data['invocations'][1]['disposition'] = 'unused'
        self.assertEqual(self.reconcile(), 'unknown')


class CallerOptInTest(EvidenceFixture, unittest.TestCase):
    """Persisted RequiredModelAssurance at build/Warden caller boundaries."""

    def setUp(self):
        super().setUp()
        self.path = Path(self.tmp.name, 'caller-inv.json')
        self.digest = write_inventory(self.path, self.data, terminal=True)
        self.marker = {'Verdict': 'PASS', 'MarkerFinality': 'final-integration', 'RunID': 'run-1',
                       'ArtifactHash': 'a' * 64, 'FinalArtifactHash': 'b' * 64, 'ModelAssurance': 'verified',
                       'ModelAssuranceInventory': f'{self.path} sha256:{self.digest}',
                       'Gated-Files': json.dumps(['a.txt'])}
        self.trusted = {'evidence': self.evidence, 'allowlist': self.allowlist, 'policy': self.POLICY,
                        'host_adapter': self.adapter}

    def allowed(self, marker=None, requirement='qg-verified', digest=None, final='b' * 64, **extra):
        extra.setdefault('expected_gated', ['a.txt'])
        return caller_allowed(requirement, self.marker if marker is None else marker, self.path,
                              digest or self.digest, final, **{**self.trusted, **extra})

    def test_baseline_is_allowed(self):
        self.assertTrue(self.allowed())
        self.assertTrue(action_allowed('qg-verified', self.marker, self.path, self.digest, 'b' * 64,
                                       evidence=self.evidence, allowlist=self.allowlist, policy=self.POLICY,
                                       host_adapter=self.adapter, expected_gated=['a.txt']))

    def test_expected_gated_binds_tuple_to_artifact(self):
        # A genuine verified tuple for a.txt must not authorize a different artifact (replay, r8 S1).
        self.assertFalse(self.allowed(expected_gated=['new.md']))
        self.assertFalse(self.allowed(expected_gated=['a.txt', 'new.md']))  # code caller: a changed path never gated
        self.assertTrue(self.allowed(expected_gated=('a.txt',)))
        for missing in (None, [], (), set(), 'a.txt', [None], [b'a.txt'], [1]):
            with self.subTest(missing=missing):
                self.assertFalse(self.allowed(expected_gated=missing))
        # requirement none/absent is unaffected by the new input
        self.assertTrue(caller_allowed('none', {'Verdict': 'PASS'}, None, None, None))
        self.assertTrue(caller_allowed(None, {}, None, None, None))

    def test_legacy_and_none_never_engage(self):
        for requirement in (None, '', 'none'):
            self.assertTrue(caller_allowed(requirement, {}, None, None, None))
        marker = {'Verdict': 'FAIL'}
        frozen = dict(marker)
        self.assertTrue(caller_allowed('none', marker, None, None, None))
        self.assertEqual(marker, frozen)  # the predicate never rewrites artifact verdict state

    def test_unsupported_values_block_only_opted_in_action(self):
        self.assertFalse(self.allowed(requirement='warden-verified'))
        self.assertFalse(self.allowed(requirement='verified'))

    def test_none_bindings_block(self):
        # None never matches None: a gated_hash failure (None) or an absent marker field blocks, never falls into a provisional read.
        bare = {k: v for k, v in self.marker.items() if k != 'FinalArtifactHash'}
        self.assertFalse(self.allowed(marker=bare, final=None))
        self.assertFalse(self.allowed(final=None))
        self.assertFalse(caller_allowed('qg-verified', self.marker, self.path, None, 'b' * 64, **self.trusted))
        no_digest = {**bare, 'ModelAssuranceInventory': f'{self.path} sha256:None'}
        self.assertFalse(caller_allowed('qg-verified', no_digest, self.path, None, None, **self.trusted))
        self.assertFalse(caller_allowed('qg-verified', {**self.marker, 'ModelAssuranceInventory': f'{self.path} sha256:None'},
                                        self.path, None, 'b' * 64, **self.trusted))
        self.assertTrue(caller_allowed('none', {'Verdict': 'PASS'}, None, None, None))  # ordinary PASS is untouched

    def test_each_single_flip_blocks(self):
        flips = {
            'no adapter': dict(host_adapter=None),
            'no allowlist': dict(allowlist={}),
            'no evidence': dict(evidence={}),
            'other artifact': dict(expected_gated=['new.md']),
            'no expected_gated': dict(expected_gated=None),
            'other final hash': dict(final='c' * 64),
            'other digest': dict(digest='e' * 64),
            'chunk milestone': dict(marker={**self.marker, 'MarkerFinality': 'chunk-milestone'}),
            'missing finality': dict(marker={k: v for k, v in self.marker.items() if k != 'MarkerFinality'}),
            'wrong inventory field': dict(marker={**self.marker, 'ModelAssuranceInventory': f'{self.path} sha256:{"e" * 64}'}),
            'inventory field other path': dict(marker={**self.marker, 'ModelAssuranceInventory': f'/elsewhere sha256:{self.digest}'}),
            'marker says unknown': dict(marker={**self.marker, 'ModelAssurance': 'unknown'}),
            'roster chunk not PASS': 'roster',
            'marker not PASS': dict(marker={**self.marker, 'Verdict': 'ESCALATED'}),
            'other run in marker': dict(marker={**self.marker, 'RunID': 'run-2'}),
            'gated set omits a changed file': dict(marker={**self.marker, 'Gated-Files': json.dumps(['a.txt', 'extra.txt'])}),
            'marker without Gated-Files': dict(marker={k: v for k, v in self.marker.items() if k != 'Gated-Files'}),
            'other artifact hash in marker': dict(marker={**self.marker, 'ArtifactHash': 'c' * 64}),
        }
        for label, flip in flips.items():
            with self.subTest(label):
                if flip == 'roster':  # a verified inventory whose own roster records a non-PASS chunk
                    self.data['roster']['terminal']['c2'] = 'ESCALATED'
                    path = Path(self.tmp.name, 'esc-inv.json')
                    digest = write_inventory(path, self.data, terminal=True)
                    marker = {**self.marker, 'ModelAssuranceInventory': f'{path} sha256:{digest}'}
                    self.assertFalse(caller_allowed('qg-verified', marker, path, digest, 'b' * 64,
                                                    expected_gated=['a.txt'], **self.trusted))
                    self.data['roster']['terminal']['c2'] = 'PASS'
                    continue
                self.assertFalse(self.allowed(**flip))

    def test_document_mode_caller_flow_without_any_mode_argument(self):
        root = Path(self.tmp.name, 'docroot')  # a non-git root holding one design document
        root.mkdir()
        (root / 'design.md').write_bytes(b'design')
        self.data['gated'] = {'paths': ['design.md'], 'deleted': [], 'mode': 'document'}
        self.data['final_artifact_hash'] = gated_hash(self.data, root)
        self.assertEqual(self.data['final_artifact_hash'], hashlib.sha256(b'design').hexdigest())
        self.path = Path(self.tmp.name, 'doc-inv.json')
        digest = write_inventory(self.path, self.data, terminal=True)
        marker = {**self.marker, 'FinalArtifactHash': self.data['final_artifact_hash'],
                  'ModelAssuranceInventory': f'{self.path} sha256:{digest}', 'Gated-Files': json.dumps(['design.md'])}
        trusted = {**self.trusted, 'evidence': self.signed()}
        # Caller side: read the persisted gated set provisionally, recompute, then run the predicate.
        recomputed = gated_hash(read_inventory(self.path, digest, 'run-1', 'a' * 64, None), root)
        self.assertTrue(caller_allowed('qg-verified', marker, self.path, digest, recomputed,
                                       expected_gated=['design.md'], **trusted))
        # the same genuine tuple presented for a different phase artifact is refused
        self.assertFalse(caller_allowed('qg-verified', marker, self.path, digest, recomputed,
                                        expected_gated=['new-design.md'], **trusted))
        (root / 'design.md').write_bytes(b'edited')
        stale = gated_hash(read_inventory(self.path, digest, 'run-1', 'a' * 64, None), root)
        self.assertFalse(caller_allowed('qg-verified', marker, self.path, digest, stale,
                                        expected_gated=['design.md'], **trusted))

    def test_missing_inventory_blocks(self):
        os.unlink(self.path)
        self.assertFalse(self.allowed())


if __name__ == '__main__':
    unittest.main()
