#!/usr/bin/env python3
"""Portable QG artifact identity and no-adapter assurance checks."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

from qg_model_assurance import artifact_hash, configured_assurance, write_inventory, read_inventory, assurance_state, action_allowed, reconcile_evidence


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


class InventoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name, 'run.json')
        self.data = {
            'version': 1, 'run_id': 'run-1', 'artifact_hash': 'a' * 64,
            'final_artifact_hash': 'b' * 64,
            'roster': {'kind': 'single-artifact', 'chunks': ['artifact'], 'terminal': ['artifact'], 'consensus': []},
            'invocations': [{'id': 'round-1-review', 'parent': 'run-1', 'scope': 'artifact/round-1',
                             'disposition': 'consumed', 'assurance': 'unknown'}],
        }

    def test_write_readback_and_absent_host_evidence(self):
        digest = write_inventory(self.path, self.data)
        self.assertEqual(read_inventory(self.path, digest, 'run-1', 'a' * 64, 'b' * 64), self.data)
        self.assertEqual(assurance_state(self.data), 'unknown')
        self.data['invocations'][0]['assurance'] = 'configured'
        self.assertEqual(assurance_state(self.data), 'unknown')
        self.data['invocations'][0]['request'] = {'model': 'provider/model', 'effort': 'high', 'route': 'fixed'}
        policy = {'provider/model': {'effort': 'high', 'route': 'fixed'}}
        self.assertEqual(assurance_state(self.data, policy), 'configured')
        self.data['invocations'][0]['assurance'] = 'verified'
        self.assertEqual(assurance_state(self.data, policy), 'unknown')

    def test_tamper_and_binding_fail_closed(self):
        digest = write_inventory(self.path, self.data)
        for args in [(digest, 'other', 'a' * 64, 'b' * 64), (digest, 'run-1', 'c' * 64, 'b' * 64),
                     (digest, 'run-1', 'a' * 64, 'c' * 64), ('0' * 64, 'run-1', 'a' * 64, 'b' * 64)]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                read_inventory(self.path, *args)
        self.path.write_text('{}')
        with self.assertRaises(ValueError):
            read_inventory(self.path, digest, 'run-1', 'a' * 64, 'b' * 64)

    def test_opt_in_blocks_unknown_without_changing_artifact_pass(self):
        digest = write_inventory(self.path, self.data)
        marker = {'Verdict': 'PASS', 'MarkerFinality': 'final-integration', 'RunID': 'run-1',
                  'ArtifactHash': 'a' * 64, 'FinalArtifactHash': 'b' * 64,
                  'ModelAssurance': 'unknown', 'ModelAssuranceInventory': f'{self.path} sha256:{digest}'}
        self.assertTrue(action_allowed('none', marker, self.path, digest, 'b' * 64))
        self.assertFalse(action_allowed('qg-verified', marker, self.path, digest, 'b' * 64))
        self.assertFalse(action_allowed('warden-verified', marker, self.path, digest, 'b' * 64))
        self.assertFalse(action_allowed('qg-verified', {**marker, 'ModelAssurance': 'verified'}, self.path, digest, 'b' * 64))
        self.assertFalse(action_allowed('qg-verified', {**marker, 'MarkerFinality': 'chunk-milestone'}, self.path, digest, 'b' * 64))

    def test_incomplete_or_duplicate_inventory_rejected(self):
        from copy import deepcopy
        invalid = []
        for mutation in ('missing-chunk', 'duplicate-id', 'missing-parent', 'extra-consensus', 'bad-disposition'):
            data = deepcopy(self.data)
            if mutation == 'missing-chunk':
                data['roster']['terminal'] = []
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
                write_inventory(self.path, data)


class EvidenceReconciliationTest(unittest.TestCase):
    """Host-adapter evidence contract; synthetic evidence stays unknown absent trusted origin."""
    POLICY = {'provider/model': {'effort': 'high', 'route': 'fixed'}}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name, 'evidence')
        self.dir.mkdir()
        self.dir.chmod(0o700)
        self.key = self.dir / 'origin.key'
        self.key.write_bytes(b'host-owned-key')
        self.key.chmod(0o400)
        self.data = {
            'version': 1, 'run_id': 'run-1', 'artifact_hash': 'a' * 64,
            'final_artifact_hash': 'b' * 64,
            'roster': {'kind': 'chunked', 'chunks': ['c1', 'c2'], 'terminal': ['c1', 'c2'],
                       'consensus': ['synthesis']},
            'invocations': [
                {'id': 'review', 'parent': 'run-1', 'scope': 'c1', 'disposition': 'consumed', 'assurance': 'verified'},
                {'id': 'synthesis', 'parent': 'run-1', 'scope': 'c2', 'disposition': 'consumed', 'assurance': 'verified'},
                {'id': 'failed-member', 'parent': 'run-1', 'scope': 'c2', 'disposition': 'unused', 'assurance': 'unknown'},
            ],
        }
        self.allowlist = {'test-host': {'version': '2', 'key_path': str(self.key)}}
        self.journal = [
            {'id': 'review', 'run_id': 'run-1', 'disposition': 'consumed', 'result_digest': 'r' * 64},
            {'id': 'synthesis', 'run_id': 'run-1', 'disposition': 'consumed', 'result_digest': 's' * 64},
            {'id': 'failed-member', 'run_id': 'run-1', 'disposition': 'unused', 'result_digest': 'f' * 64},
        ]
        self.records = {}
        for name, digest, turns in [('review', 'r' * 64, 2), ('synthesis', 's' * 64, 1)]:
            self.put_record(name, {'id': name, 'result_digest': digest,
                                   'turns': [{'model': 'provider/model', 'effort': 'high', 'route': 'fixed'}] * turns})
        self.write_journal()
        self.evidence = self.signed()

    def put_record(self, name, record):
        path = self.dir / f'{name}.json'
        path.write_text(json.dumps(record))
        self.records[name] = {'path': str(path), 'digest': hashlib.sha256(path.read_bytes()).hexdigest()}

    def write_journal(self):
        self.journal_path = self.dir / 'journal.jsonl'
        self.journal_path.write_text(''.join(json.dumps(line) + '\n' for line in self.journal))

    def signed(self, key=b'host-owned-key', journal=None, records=None):
        journal = self.journal if journal is None else journal
        records = self.records if records is None else records
        self.journal_path.write_text(''.join(json.dumps(line) + '\n' for line in journal))
        canonical = json.dumps({'journal': journal, 'records': records},
                               sort_keys=True, separators=(',', ':')).encode()
        return {'adapter': {'name': 'test-host', 'version': '2'}, 'run_id': 'run-1',
                'origin': {'key_path': str(self.key), 'hmac': hmac.new(key, canonical, hashlib.sha256).hexdigest()},
                'journal_path': str(self.journal_path), 'records': records}

    def reconcile(self, evidence=None, allowlist=None, policy=None):
        return reconcile_evidence(self.data, evidence if evidence is not None else self.evidence,
                                  self.allowlist if allowlist is None else allowlist,
                                  self.POLICY if policy is None else policy)

    def test_complete_protected_evidence_verifies(self):
        self.assertEqual(self.reconcile(), 'verified')

    def test_production_default_fails_closed(self):
        self.assertEqual(reconcile_evidence(self.data, self.evidence, {}, self.POLICY), 'unknown')
        self.assertEqual(reconcile_evidence(self.data, {}, {}, {}), 'unknown')
        self.assertEqual(reconcile_evidence(self.data, None, None, None), 'unknown')
        self.assertEqual(self.reconcile(allowlist={'other-host': self.allowlist['test-host']}), 'unknown')
        self.assertEqual(self.reconcile(evidence={**self.evidence,
                         'adapter': {'name': 'test-host', 'version': '3'}}), 'unknown')

    def test_unauthenticated_or_child_writable_origin_unknown(self):
        self.assertEqual(self.reconcile(evidence={**self.evidence, 'origin': {**self.evidence['origin'], 'hmac': '0' * 64}}), 'unknown')
        self.assertEqual(self.reconcile(evidence=self.signed(key=b'forged-key')), 'unknown')
        self.key.chmod(0o644)
        self.assertEqual(self.reconcile(), 'unknown')
        self.key.chmod(0o400)
        self.dir.chmod(0o775)
        self.assertEqual(self.reconcile(), 'unknown')

    def test_multi_turn_mismatch_and_mixed_effort(self):
        self.put_record('review', {'id': 'review', 'result_digest': 'r' * 64,
                                   'turns': [{'model': 'provider/model', 'effort': 'high', 'route': 'fixed'},
                                             {'model': 'provider/other', 'effort': 'high', 'route': 'fixed'}]})
        self.assertEqual(self.reconcile(evidence=self.signed()), 'unknown')
        self.put_record('review', {'id': 'review', 'result_digest': 'r' * 64,
                                   'turns': [{'model': 'provider/model', 'effort': 'low', 'route': 'fixed'}]})
        self.assertEqual(self.reconcile(evidence=self.signed()), 'unknown')
        self.put_record('review', {'id': 'review', 'result_digest': 'r' * 64, 'turns': []})
        self.assertEqual(self.reconcile(evidence=self.signed()), 'unknown')

    def test_injected_duplicate_or_replayed_journal(self):
        injected = self.journal + [{'id': 'ghost', 'run_id': 'run-1', 'disposition': 'consumed', 'result_digest': 'g' * 64}]
        self.assertEqual(self.reconcile(evidence=self.signed(journal=injected)), 'unknown')
        duplicated = self.journal + [dict(self.journal[0])]
        self.assertEqual(self.reconcile(evidence=self.signed(journal=duplicated)), 'unknown')
        replayed = [dict(line, replay=True) if line['id'] == 'synthesis' else line for line in self.journal]
        self.assertEqual(self.reconcile(evidence=self.signed(journal=replayed)), 'unknown')
        self.write_journal()

    def test_missing_stale_or_unavailable_records(self):
        os.unlink(self.records['review']['path'])
        self.assertEqual(self.reconcile(), 'unknown')
        self.put_record('review', {'id': 'review', 'result_digest': 'r' * 64,
                                   'turns': [{'model': 'provider/model', 'effort': 'high', 'route': 'fixed'}]})
        stale = self.signed()
        Path(self.records['review']['path']).write_text('{"tampered": true}')
        self.assertEqual(self.reconcile(evidence=stale), 'unknown')
        os.unlink(self.journal_path)
        self.assertEqual(self.reconcile(), 'unknown')
        self.write_journal()
        self.journal_path.write_text('not-json\n')
        self.assertEqual(self.reconcile(), 'unknown')

    def test_wrong_run_or_dispatch_binding(self):
        self.assertEqual(self.reconcile(evidence={**self.evidence, 'run_id': 'run-2'}), 'unknown')
        rebound = [dict(line, run_id='run-2') if line['id'] == 'review' else line for line in self.journal]
        self.assertEqual(self.reconcile(evidence=self.signed(journal=rebound)), 'unknown')
        self.put_record('review', {'id': 'other-invocation', 'result_digest': 'r' * 64,
                                   'turns': [{'model': 'provider/model', 'effort': 'high', 'route': 'fixed'}]})
        self.assertEqual(self.reconcile(evidence=self.signed()), 'unknown')

    def test_look_harder_demotion_and_consensus_membership(self):
        self.data['invocations'].append({'id': 'look-harder', 'parent': 'run-1', 'scope': 'c1',
                                         'disposition': 'consumed', 'assurance': 'verified'})
        self.journal.append({'id': 'look-harder', 'run_id': 'run-1', 'disposition': 'consumed', 'result_digest': 'l' * 64})
        self.put_record('look-harder', {'id': 'look-harder', 'result_digest': 'l' * 64,
                                        'turns': [{'model': 'provider/model', 'effort': 'high', 'route': 'fixed'}]})
        self.write_journal()
        self.assertEqual(self.reconcile(evidence=self.signed()), 'verified')
        demoted = [dict(line, disposition='unused') if line['id'] == 'synthesis' else line
                   for line in self.journal]
        self.assertEqual(self.reconcile(evidence=self.signed(journal=demoted)), 'unknown')

    def test_action_allowed_opt_in_with_and_without_evidence(self):
        path = Path(self.tmp.name, 'inv.json')
        digest = write_inventory(path, self.data)
        marker = {'Verdict': 'PASS', 'MarkerFinality': 'final-integration', 'RunID': 'run-1',
                  'ArtifactHash': 'a' * 64, 'FinalArtifactHash': 'b' * 64, 'ModelAssurance': 'verified',
                  'ModelAssuranceInventory': f'{path} sha256:{digest}'}
        self.assertTrue(action_allowed('qg-verified', marker, path, digest, 'b' * 64,
                                       evidence=self.evidence, allowlist=self.allowlist, policy=self.POLICY))
        self.assertFalse(action_allowed('qg-verified', marker, path, digest, 'b' * 64))
        self.assertFalse(action_allowed('qg-verified', marker, path, digest, 'b' * 64,
                                        evidence=self.evidence, allowlist={}, policy=self.POLICY))
        self.assertTrue(action_allowed('none', marker, path, digest, 'b' * 64))

if __name__ == '__main__':
    unittest.main()
