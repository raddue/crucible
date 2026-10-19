#!/usr/bin/env python3
"""Portable QG artifact identity and no-adapter assurance checks."""
import hashlib
import hmac
from unittest import mock
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

import qg_model_assurance as qma
from qg_model_assurance import (artifact_hash, configured_assurance, write_inventory, read_inventory, assurance_state,
                                action_allowed, reconcile_evidence, caller_allowed, canonical_evidence, gated_hash)


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


GATED = {'paths': ['a.txt', 'gone'], 'deleted': ['gone']}


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
                             'disposition': 'consumed', 'assurance': 'unknown'}],
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
            'deleted outside gated set': lambda d: d.update(gated={'paths': ['a'], 'deleted': ['b']}),
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
        self.data = {
            'version': 1, 'run_id': 'run-1', 'artifact_hash': 'a' * 64,
            'final_artifact_hash': 'b' * 64, 'gated': GATED,
            'roster': {'kind': 'chunked', 'chunks': ['c1', 'c2'], 'terminal': {'c1': 'PASS', 'c2': 'PASS'},
                       'consensus': ['synthesis']},
            'invocations': [
                {'id': 'review', 'parent': 'run-1', 'scope': 'c1', 'disposition': 'consumed', 'assurance': 'verified'},
                {'id': 'synthesis', 'parent': 'run-1', 'scope': 'c2', 'disposition': 'consumed', 'assurance': 'verified'},
                {'id': 'failed-member', 'parent': 'run-1', 'scope': 'c2', 'disposition': 'unused', 'assurance': 'unknown'},
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
        self.assertEqual(self.reconcile(adapter=FakeAdapter({self.real_uid + 1})), 'unknown')  # not the owner
        self.assertEqual(self.reconcile(adapter=FakeAdapter(set())), 'unknown')

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

    def test_journal_over_cap_unknown(self):
        flood = self.journal + [{'id': f'x{i}', 'run_id': 'run-1', 'disposition': 'unused', 'result_digest': '3' * 64}
                                for i in range(qma.MAX_INVOCATIONS)]
        self.assertEqual(self.reconcile(evidence=self.signed(journal=flood)), 'unknown')

    def test_multi_turn_mismatch_and_mixed_effort(self):
        for turns in ([self.TURN, {**self.TURN, 'model': 'provider/other'}], [{**self.TURN, 'effort': 'low'}], []):
            self.put_record('review', {'id': 'review', 'result_digest': '1' * 64, 'turns': turns})
            self.assertEqual(self.reconcile(evidence=self.signed()), 'unknown')

    def test_injected_duplicate_or_replayed_journal(self):
        injected = self.journal + [{'id': 'ghost', 'run_id': 'run-1', 'disposition': 'consumed', 'result_digest': '4' * 64}]
        self.assertEqual(self.reconcile(evidence=self.signed(journal=injected)), 'unknown')
        duplicated = self.journal + [dict(self.journal[0])]
        self.assertEqual(self.reconcile(evidence=self.signed(journal=duplicated)), 'unknown')
        replayed = [dict(line, replay=True) if line['id'] == 'synthesis' else line for line in self.journal]
        self.assertEqual(self.reconcile(evidence=self.signed(journal=replayed)), 'unknown')

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
                                         'disposition': 'consumed', 'assurance': 'verified'})
        self.journal.append({'id': 'look-harder', 'run_id': 'run-1', 'disposition': 'consumed', 'result_digest': '5' * 64})
        self.put_record('look-harder', {'id': 'look-harder', 'result_digest': '5' * 64, 'turns': [self.TURN]})
        self.assertEqual(self.reconcile(evidence=self.signed()), 'verified')
        demoted = [dict(line, disposition='unused') if line['id'] == 'synthesis' else line
                   for line in self.journal]
        self.assertEqual(self.reconcile(evidence=self.signed(journal=demoted)), 'unknown')

    def test_consensus_member_unused_in_inventory_unknown(self):
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
                       'ModelAssuranceInventory': f'{self.path} sha256:{self.digest}'}
        self.trusted = {'evidence': self.evidence, 'allowlist': self.allowlist, 'policy': self.POLICY,
                        'host_adapter': self.adapter}

    def allowed(self, marker=None, requirement='qg-verified', digest=None, final='b' * 64, **extra):
        return caller_allowed(requirement, self.marker if marker is None else marker, self.path,
                              digest or self.digest, final, **{**self.trusted, **extra})

    def test_baseline_is_allowed(self):
        self.assertTrue(self.allowed())
        self.assertTrue(action_allowed('qg-verified', self.marker, self.path, self.digest, 'b' * 64,
                                       evidence=self.evidence, allowlist=self.allowlist, policy=self.POLICY,
                                       host_adapter=self.adapter))

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

    def test_each_single_flip_blocks(self):
        flips = {
            'no adapter': dict(host_adapter=None),
            'no allowlist': dict(allowlist={}),
            'no evidence': dict(evidence={}),
            'wrong run': dict(expected_run_id='run-2'),
            'other final hash': dict(final='c' * 64),
            'other digest': dict(digest='e' * 64),
            'chunk milestone': dict(marker={**self.marker, 'MarkerFinality': 'chunk-milestone'}),
            'missing finality': dict(marker={k: v for k, v in self.marker.items() if k != 'MarkerFinality'}),
            'wrong inventory field': dict(marker={**self.marker, 'ModelAssuranceInventory': f'{self.path} sha256:{"e" * 64}'}),
            'inventory field other path': dict(marker={**self.marker, 'ModelAssuranceInventory': f'/elsewhere sha256:{self.digest}'}),
            'marker says unknown': dict(marker={**self.marker, 'ModelAssurance': 'unknown'}),
            'marker not PASS': dict(marker={**self.marker, 'Verdict': 'ESCALATED'}),
            'other run in marker': dict(marker={**self.marker, 'RunID': 'run-2'}),
            'other artifact hash in marker': dict(marker={**self.marker, 'ArtifactHash': 'c' * 64}),
        }
        for label, flip in flips.items():
            with self.subTest(label):
                self.assertFalse(self.allowed(**flip))

    def test_missing_inventory_blocks(self):
        os.unlink(self.path)
        self.assertFalse(self.allowed())


if __name__ == '__main__':
    unittest.main()
