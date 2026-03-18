import { describe, it, expect } from 'vitest';
import { readFileSync, existsSync } from 'fs';
import { join } from 'path';

const SKILL_DIR = join(__dirname, '../../skills/pathfinder');
const SKILL_MD = join(SKILL_DIR, 'SKILL.md');

function readSkill(): string {
  return readFileSync(SKILL_MD, 'utf-8');
}

describe('Pathfinder Crawl Mode — Acceptance Tests', () => {
  // AC12: Given a seed repo with known dependencies, crawl mode discovers connected repos via forward fan-out
  describe('crawl mode exists in skill definition', () => {
    it('SKILL.md defines three modes including crawl', () => {
      const skill = readSkill();
      expect(skill).toMatch(/three modes/i);
      expect(skill).toMatch(/crawl/i);
    });

    it('crawl invocation syntax is documented', () => {
      const skill = readSkill();
      expect(skill).toMatch(/crucible:pathfinder crawl <org>\/<repo>/);
    });

    it('documents --depth and --orgs parameters', () => {
      const skill = readSkill();
      expect(skill).toMatch(/--depth/);
      expect(skill).toMatch(/--orgs/);
    });
  });

  // AC13: Given a seed repo that is called by other repos, crawl mode discovers callers via reverse search
  describe('bidirectional crawl — forward and reverse', () => {
    it('documents fan-out (forward) analysis', () => {
      const skill = readSkill();
      expect(skill).toMatch(/fan-out|forward/i);
    });

    it('documents fan-in (reverse) search', () => {
      const skill = readSkill();
      expect(skill).toMatch(/fan-in|reverse search/i);
    });

    it('documents identity signals for reverse search', () => {
      const skill = readSkill();
      expect(skill).toMatch(/identity.signals/i);
    });
  });

  // AC14: Crawl respects depth limits and stops when no new repos are found
  describe('depth control', () => {
    it('documents default and max depth limits', () => {
      const skill = readSkill();
      expect(skill).toMatch(/default:\s*3/i);
      expect(skill).toMatch(/max:\s*10/i);
    });

    it('documents natural termination when no new repos found', () => {
      const skill = readSkill();
      expect(skill).toMatch(/no new repos/i);
    });
  });

  // AC15: User checkpoint after each depth level
  describe('user checkpoints', () => {
    it('documents checkpoint after each depth level', () => {
      const skill = readSkill();
      expect(skill).toMatch(/checkpoint.*depth|depth.*checkpoint/i);
    });
  });

  // AC16: Ambiguous references batched and presented at checkpoints
  describe('ambiguous reference handling', () => {
    it('documents interactive fallback for unresolved references', () => {
      const skill = readSkill();
      expect(skill).toMatch(/unresolved|ambiguous/i);
    });
  });

  // AC17: Crawl results merge without marking non-crawled repos stale
  describe('merge with existing topology', () => {
    it('documents crawl-aware merge rules', () => {
      const skill = readSkill();
      expect(skill).toMatch(/stale/i);
      // Crawl should NOT stale-mark repos not found in crawl
      expect(skill).toMatch(/not.*stale|no.*stale-marking/i);
    });
  });

  // AC18: Crawl state survives compaction including resolution decisions
  describe('state management and compaction recovery', () => {
    it('uses unified state file with mode discriminator', () => {
      const skill = readSkill();
      expect(skill).toMatch(/"mode":\s*"crawl"/);
    });

    it('documents compaction recovery for crawl mode', () => {
      const skill = readSkill();
      expect(skill).toMatch(/compaction.*crawl|crawl.*compaction/i);
    });

    it('documents resolution persistence in state file', () => {
      const skill = readSkill();
      expect(skill).toMatch(/resolution.*pending|resolution.*field/i);
    });
  });

  // AC19: Higher importance repos analyzed first
  describe('frontier prioritization', () => {
    it('documents importance scoring', () => {
      const skill = readSkill();
      expect(skill).toMatch(/importance|prioriti/i);
    });

    it('documents scoring factors: density, diversity, bridging', () => {
      const skill = readSkill();
      expect(skill).toMatch(/signal density/i);
      expect(skill).toMatch(/signal diversity/i);
      expect(skill).toMatch(/bridging/i);
    });
  });

  // AC20: Adaptive termination recommends stopping when all candidates score LOW
  describe('adaptive depth termination', () => {
    it('documents LOW_THRESHOLD with a defined value', () => {
      const skill = readSkill();
      expect(skill).toMatch(/LOW_THRESHOLD\s*=\s*2/);
    });

    it('documents adaptive termination as recommendation, not automatic', () => {
      const skill = readSkill();
      expect(skill).toMatch(/recommendation.*not.*automatic|never automatic/i);
    });
  });

  // AC21: Single-org notice when --orgs omitted
  describe('single-org reverse search notice', () => {
    it('documents explicit notice when --orgs is omitted', () => {
      const skill = readSkill();
      expect(skill).toMatch(/reverse search will only cover/i);
    });
  });

  // AC22: Tier 2 offered after all crawl depth levels, before synthesis
  describe('Tier 2 opt-in during crawl', () => {
    it('documents when Tier 2 is offered in crawl mode', () => {
      const skill = readSkill();
      expect(skill).toMatch(/tier 2.*crawl|crawl.*tier 2/i);
    });
  });

  // Prompt templates
  describe('required prompt templates exist', () => {
    it('reverse-search-prompt.md exists', () => {
      expect(existsSync(join(SKILL_DIR, 'reverse-search-prompt.md'))).toBe(true);
    });

    it('tier1-analyzer-prompt.md includes identity_signals output', () => {
      const tier1 = readFileSync(join(SKILL_DIR, 'tier1-analyzer-prompt.md'), 'utf-8');
      expect(tier1).toMatch(/identity.signals/i);
    });
  });

  // Agent dispatch
  describe('agent dispatch table includes crawl agents', () => {
    it('documents Reverse Searcher agent', () => {
      const skill = readSkill();
      expect(skill).toMatch(/Reverse Searcher/);
    });
  });

  // Output directories
  describe('output directory conventions', () => {
    it('documents crawl-specific output directory pattern', () => {
      const skill = readSkill();
      expect(skill).toMatch(/crawl-<seed-repo>/);
    });

    it('documents persistence path for crawl results', () => {
      const skill = readSkill();
      expect(skill).toMatch(/~\/.claude\/memory\/pathfinder/);
    });
  });

  // Crawl-specific narration
  describe('communication requirement includes crawl examples', () => {
    it('includes crawl-specific narration examples', () => {
      const skill = readSkill();
      expect(skill).toMatch(/Crawl.*Seed|Crawl.*Depth/);
    });
  });

  // Synthesis augmentation
  describe('synthesis supports crawl metadata', () => {
    it('documents crawl metadata passed to synthesis agent', () => {
      const skill = readSkill();
      expect(skill).toMatch(/crawl_metadata|crawl.metadata|discovery.path/i);
    });
  });

  // Error handling
  describe('crawl-specific error handling', () => {
    it('documents seed repo not found error', () => {
      const skill = readSkill();
      expect(skill).toMatch(/seed repo.*not found/i);
    });

    it('documents code search unavailable error', () => {
      const skill = readSkill();
      expect(skill).toMatch(/code search unavailable/i);
    });

    it('documents seed with no manifests fallback', () => {
      const skill = readSkill();
      expect(skill).toMatch(/no.*manifest|no.*identity signal/i);
    });
  });
});
