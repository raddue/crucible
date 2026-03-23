# Prospector Reference

This is the canonical knowledge base for the prospector skill. Analysis agents and the orchestrator consult this document during friction classification, philosophy mapping, constraint selection, dependency categorization, and origin typing.

---

## Friction Taxonomy

The five friction types the prospector recognizes. Each entry includes a description, detection signals, and severity indicators.

### Shallow Modules

**Description:** A module's interface is nearly as complex as its implementation. The abstraction provides little leverage — callers must understand the full internals anyway, because the interface exposes everything.

**Detection signals:**
- High public-method-to-internal-method ratio
- Understanding one concept requires reading many small files
- Interface surface area rivals the implementation in size and complexity
- Callers pass through parameters without transformation

**Severity indicators:** Scales with the number of callers. A shallow module with 20 callers creates widespread navigational friction; the same problem with 2 callers is minor.

---

### Coupling / Shotgun Surgery

**Description:** Changing one behavior requires edits across many unrelated files. The codebase lacks clear ownership boundaries — a single conceptual change fans out into multiple disconnected locations.

**Detection signals:**
- Co-change patterns in git history (files that always change together but aren't logically related)
- Shared mutable state accessed from many locations
- Circular dependencies between modules
- Ripple effects from single-line changes
- High number of files touched per commit in an area

**Severity indicators:** Scales with change frequency in the area. High-velocity code with coupling is a constant tax; stable legacy code with coupling is latent risk.

---

### Leaky Abstraction

**Description:** An abstraction exists but callers must understand its internals to use it correctly. The abstraction nominally hides complexity but fails to do so in practice — callers end up reasoning about implementation details anyway.

**Detection signals:**
- Callers handling format-specific edge cases that should be the abstraction's responsibility
- Internal types exposed in the public API
- Configuration options that exceed the problem the abstraction is supposed to solve
- Documentation that explains how the abstraction works instead of how to use it

**Severity indicators:** Scales with the abstraction's centrality. A leaky abstraction in a core library affects every consumer; a leaky abstraction in a utility module has limited blast radius.

---

### Testability Barrier

**Description:** Testing requires elaborate mock setups that mirror internal structure. Tests are fragile because they're coupled to implementation details rather than observable behavior.

**Detection signals:**
- Mock complexity proportional to implementation complexity (10-step mock setup to test one behavior)
- Test breakage on internal refactors that don't change observable behavior
- Pure functions extracted for testability, but real bugs hide in how those functions are called
- Test files longer than implementation files

**Severity indicators:** Scales with test maintenance burden. A testability barrier in frequently-changed code creates constant friction; in stable code it's a one-time cost.

---

### Scattered Domain

**Description:** A single domain concept is spread across multiple layers with no clear owner. No single module can answer questions about the concept — understanding it requires reading across many locations.

**Detection signals:**
- The same business term appears in 3+ directories with no canonical source
- No single module can authoritatively answer questions about the domain concept
- Changes to the concept require multi-layer edits (controller, service, repository, DTO all touch the concept separately)
- Business rules for the concept are duplicated or inconsistently applied

**Severity indicators:** Scales with the concept's importance to the business. A scattered core domain concept is high severity; a scattered peripheral concept is medium.

---

## Philosophy Framework Mappings

For each friction type, the applicable architectural philosophy and a brief explanation of why it applies. Analysis agents use this to ground their recommendations in established thinking.

### Shallow Modules → Ousterhout Deep Modules

**Source:** John Ousterhout, "A Philosophy of Software Design"

**Why it applies:** Ousterhout's central argument is that good module design maximizes the ratio of functionality hidden to interface exposed. A deep module hides a large implementation behind a small, simple interface. Shallow modules invert this — they expose nearly as much as they implement, providing no hiding benefit. The remedy is consolidation: merge shallow modules so the aggregate interface is smaller than the aggregate implementation.

---

### Coupling / Shotgun Surgery → Martin Coupling and Cohesion

**Source:** Robert C. Martin, "Clean Architecture"

**Why it applies:** Martin's Stable Dependencies Principle and Common Closure Principle address exactly this failure mode. Code that changes together should live together (Common Closure). Dependencies should flow toward stability, not scatter laterally across unrelated modules. Shotgun surgery is the observable symptom of violated Common Closure — the fix is to identify what concept is actually changing and give it a single home.

---

### Leaky Abstraction → Spolsky's Law of Leaky Abstractions

**Source:** Joel Spolsky, "The Law of Leaky Abstractions" (2002)

**Why it applies:** Spolsky's law states that all non-trivial abstractions leak — the underlying complexity bleeds through the interface under certain conditions. The practical implication is that callers of any abstraction must eventually understand what's underneath it. The remedy is not to eliminate abstractions but to minimize how much they leak: either seal the interface completely, replace the abstraction with a simpler direct approach, or use Ports & Adapters to make the leak an explicit, injectable boundary.

---

### Testability Barrier → Dependency Inversion Principle

**Source:** SOLID principles (Robert C. Martin)

**Why it applies:** The Dependency Inversion Principle (DIP) states that high-level modules should not depend on low-level modules — both should depend on abstractions. Testability barriers arise when high-level logic is directly coupled to concrete dependencies, making those dependencies impossible to substitute in tests. Applying DIP — expressing dependencies as interfaces and injecting concrete implementations — makes the boundaries explicit and substitutable, which is what testing requires.

---

### Scattered Domain → Domain-Driven Design Bounded Contexts

**Source:** Eric Evans, "Domain-Driven Design"

**Why it applies:** DDD's Bounded Context pattern addresses the core problem: a domain concept should have a single canonical home, a ubiquitous language within that boundary, and explicit contracts at its edges. Scattered domain friction is what happens when there are no bounded contexts — the concept bleeds across layers and directories, accumulating inconsistent representations. The fix is to identify the domain boundary, aggregate the concept into it, and make cross-boundary access explicit.

---

## Constraint Menu

The deterministic friction-type-to-constraint mapping. When the orchestrator identifies a friction type classification, it looks up that type here and dispatches three competing design agents — one per constraint. This is a routing decision, not a creative one.

### Constraint Table

| Friction Type | Constraint 1 | Constraint 2 | Constraint 3 |
|---|---|---|---|
| Shallow modules | Minimize interface (1-3 entry points) | Optimize for most common caller | Hide maximum implementation detail |
| Coupling / shotgun surgery | Consolidate into single module | Introduce facade pattern | Extract shared abstraction with clean boundary |
| Leaky abstraction | Seal the abstraction (hide all internals) | Replace with simpler direct approach | Ports & adapters (injectable boundary) |
| Testability barrier | Boundary-test-friendly interface | Dependency-injectable design | Pure-function extraction with integration wrapper |
| Scattered domain | Aggregate into domain module | Event-driven decoupling | Layered with clear ownership per layer |

### Generic Fallback (Unclassified Friction)

When friction cannot be classified into one of the five types above, use these three generic constraints:

1. **Minimize interface** — Reduce the public surface area
2. **Maximize flexibility** — Make it easy to change independently
3. **Optimize for most common caller** — Shape the interface around the 80% case

---

## Dependency Categories

The four dependency categories used to classify what a module depends on. The category determines the appropriate testing strategy for any design proposal. Genealogist and analysis agents classify each friction point's dependencies before design agents select a testing approach.

### In-Process

**Definition:** Pure computation, in-memory state, no I/O of any kind.

**Testing implications:** Test directly. No mocks, no stubs, no fakes required. Call the function, assert the result.

**Examples:** Validation logic, data transformation, sorting, filtering, mathematical computations, string manipulation.

---

### Local-Substitutable

**Definition:** Dependencies that have local test stand-ins — real alternatives that can run in the test environment without requiring network access or external services.

**Testing implications:** Use a local stand-in in the test suite. The stand-in should be a real implementation, not a mock.

**Examples:** SQLite as a stand-in for Postgres, an in-memory filesystem for real disk I/O, an embedded message broker for a network queue.

---

### Remote but Owned (Ports and Adapters)

**Definition:** Your own services across a network boundary — infrastructure you control but that lives outside the current process.

**Testing implications:** Use an in-memory adapter that implements the same port (interface). The adapter lives in the test suite and simulates the remote service's behavior without crossing the network.

**Examples:** Internal microservices, internal APIs, your own event bus, your own data warehouse.

---

### True External (Mock)

**Definition:** Third-party services you do not control and cannot substitute with a local equivalent.

**Testing implications:** Mock at the boundary. Define the expected calls and responses in test fixtures. Do not attempt to replicate the external service's behavior.

**Examples:** Stripe payment processing, Twilio SMS, AWS S3 object storage, GitHub API, Salesforce.

---

## Origin Type Definitions

The six genealogy origin types used by the genealogist agent to classify how a friction point developed over time. Detection heuristics are provided for each type to guide git archaeology.

### Incomplete Migration

**Description:** A large refactoring was started but never finished. Half the codebase uses the new pattern, half still uses the old one. The friction arises from the coexistence of two inconsistent approaches.

**Detection heuristics:**
- A large refactoring commit followed by no follow-up commits addressing the same concern
- Half the callers updated to a new pattern; half still use the old pattern
- TODO comments referencing migration steps that were never completed
- A new abstraction introduced that coexists with the old abstraction it was supposed to replace

**Remediation effort implication:** Typically lower effort — the design direction is already decided, the work is completion rather than invention.

---

### Accretion

**Description:** No single commit is responsible. The friction built gradually over 10+ commits by multiple authors. Each individual commit was reasonable in isolation, but the cumulative effect created a tangle.

**Detection heuristics:**
- No single commit responsible for the friction
- Friction built gradually over 10 or more commits by multiple authors
- Each commit, viewed in isolation, appears individually reasonable
- The tangle only becomes visible when you look at the accumulated state

**Remediation effort implication:** Typically higher effort — there is no prior design direction to follow, and the accumulated complexity must be disentangled from scratch.

---

### Forced Marriage

**Description:** Two unrelated concerns were coupled in a single feature commit, usually under time pressure. The coupling was expedient at the time but created structural debt.

**Detection heuristics:**
- Two unrelated concerns coupled in a single large feature commit
- Commit message references time pressure, a deadline, or a quick fix
- The PR was large and cross-cutting across many files
- The coupling persists only because separating it was never prioritized

**Remediation effort implication:** Medium effort — the concerns are identifiable and separable, but the separation requires careful interface design.

---

### Vestigial Structure

**Description:** The old architecture was replaced, but its scaffolding remains. The friction comes from supporting dead code, obsolete configuration, or legacy abstractions that nobody uses anymore.

**Detection heuristics:**
- Old architecture replaced by a newer approach, but the old scaffolding was never removed
- Dead code paths that were formerly active but are no longer reachable
- Configuration for systems that are no longer in use
- Adapters or wrappers for dependencies that were migrated away

**Remediation effort implication:** Typically lower effort — deletion is usually safer and faster than redesign.

---

### Original Sin

**Description:** The friction was present in the initial implementation of the file or module. It was never a good design; it started as friction and accumulated more on top.

**Detection heuristics:**
- Friction present in the initial commit of the file or module
- No subsequent commits addressed the structural problem
- No prior art exists in the repository that would have guided a better design at the time

**Remediation effort implication:** Typically higher effort — the design must be invented from scratch, and there is no migration path to follow.

---

### Indeterminate

**Description:** The git history is insufficient to determine how the friction developed. The classification cannot be made with confidence.

**Detection heuristics:**
- Shallow clone with fewer than 10 commits visible for the files in question
- Squash-only merge history that collapses all development into single commits
- Less than 6 months of history available
- History present but does not reveal causal sequence

**Remediation effort implication:** Effort estimate must rely on structural analysis alone. Do not force a classification — Indeterminate with clear reasoning is more useful than a wrong classification.

---

## Testing Philosophy

### Replace, Don't Layer

When a restructured module has boundary tests that verify behavior through its public interface, old unit tests on the former shallow modules become redundant. Do not layer new tests on top of old ones — replace them.

**Core principle:** New tests assert on observable outcomes, not internal state. A well-designed boundary test exercises the module through its public interface and makes no assumptions about how the internals are organized. If an internal refactor breaks a test without changing observable behavior, that test was testing the wrong thing.

**Corollary:** Tests should survive internal refactors. If restructuring a module's internals requires rewriting its tests, those tests were coupled to implementation details rather than behavior. The goal of the "replace, don't layer" principle is to produce a test suite that is stable under refactoring — a suite that proves behavior is preserved, not that a specific internal structure exists.

**Practical application:** When design agents propose a new interface, their testing strategy should describe what the boundary tests assert — the inputs and the expected observable outputs — not which internal functions to call. The dependency category determines what test infrastructure is required (direct call, local stand-in, in-memory adapter, or mock at boundary), but the assertion logic should always target observable outcomes.

---

## Root Cause Type Taxonomy

The five root cause types used by the root cause analysis agent (Phase 2) to classify the underlying architectural decision or missing pattern that produces observed friction. These are distinct from the genealogy origin types (which classify HOW friction developed over time) — root cause types classify WHAT the architectural problem is.

### Missing or Underused Pattern

**Description:** A known pattern exists in the ecosystem (or even in the codebase) that would solve this friction, but the affected code uses a manual or inferior approach instead.

**Detection signals:**
- The project's framework documentation describes a pattern that addresses the friction point
- Other parts of the codebase use the pattern, but the friction area does not
- The manual approach replicates functionality that the framework provides natively

**Examples:** VContainer's IInitializable for self-registration when the project uses manual wiring; built-in middleware pattern when the project hand-rolls auth checks in each route handler.

**Design implication:** One constraint slot is replaced with "Adopt framework-native pattern: [specific pattern]" — a specific adoption constraint naming the exact pattern to adopt.

---

### Wrong Abstraction

**Description:** An abstraction exists but it models the wrong concept. The friction arises not from the absence of abstraction but from the abstraction modeling something other than the actual domain concern.

**Detection signals:**
- The abstraction's name does not match what callers actually use it for
- Callers routinely work around the abstraction rather than through it
- The abstraction was created for a different purpose and repurposed

**Examples:** Extracting "initializers" as an abstraction when the problem is centralized wiring; creating a "BaseService" when the shared concern is actually data validation.

**Design implication:** One constraint slot is replaced with "Replace abstraction with correct domain model: [domain concept from surviving hypothesis]."

---

### Absent Boundary

**Description:** No module boundary exists where one should. Business rules, orchestration logic, and implementation details are intermixed in the same location with no separation.

**Detection signals:**
- A single file or class handles multiple unrelated concerns
- Business rules are embedded in infrastructure code (controllers, handlers, adapters)
- No clear interface separates "what" from "how"

**Examples:** Business rules scattered across controllers with no domain layer; orchestration logic and policy logic intermixed in a god-class.

**Design implication:** One constraint slot is replaced with "Introduce boundary at [identified seam from surviving hypothesis]."

---

### Misaligned Ownership

**Description:** A module boundary exists, but the wrong module owns the concept. The friction arises from responsibility being assigned to the wrong location, causing callers to reach across boundaries to get what they need.

**Detection signals:**
- Callers frequently access internals of module B to perform operations that should be module A's responsibility
- A concept is "owned" by a module that doesn't actually understand it
- Cross-module calls that should be intra-module calls

**Examples:** Auth checks in route handlers instead of middleware; validation logic in the persistence layer instead of the domain layer.

**Design implication:** No automatic constraint override — too context-dependent. Standard friction-type mapping applies.

---

### Other / Constraint-Driven

**Description:** The root cause is an external constraint, not an internal design flaw. The friction is produced by forces outside the team's design authority — performance requirements, backward compatibility mandates, organizational boundaries, regulatory requirements.

**Detection signals:**
- The friction exists because of a deliberate trade-off that was correct at the time
- Changing the design would violate an external constraint
- The "fix" requires changing something the team does not control

**Examples:** Performance requirement forcing denormalization; backward compatibility preventing API cleanup; organizational boundary requiring code duplication between teams.

**Design implication:** No automatic constraint override. When this type is selected, the root cause agent must provide a freeform root cause statement explaining the constraint. Candidate presentation includes a warning: "Root cause is an external constraint — designs address symptoms, not the underlying cause."

---

## ROI and Leverage Scoring

Definitions and scoring rules for the ROI assessment performed by analysis agents in Phase 3.

### Leverage vs Impact

- **Impact** = How much does fixing this improve the area where the friction exists?
- **Leverage** = How much does fixing this improve everything else? How many future changes does it unblock or simplify?

Test infrastructure is high-leverage (force multiplier for all future work). God-class decomposition is high-impact but may be low-leverage (improves the god-class area but doesn't unblock other work).

### Scoring Table

| Level | Score |
|---|---|
| High | 3 |
| Medium | 2 |
| Low | 1 |

### Candidate Ranking Formula

**Formula:** `Score = leverage_score x modification_friction_score`

- Leverage and modification friction are each mapped to their numeric score (High=3, Medium=2, Low=1).
- Effort is NOT included in the formula. Effort is presented separately as a cost indicator in candidate presentation. This prevents effort from dominating the ranking signal — easy wins should not automatically outrank hard necessities.
- Ties are broken by comprehension friction score (higher comprehension friction ranks first among tied candidates).
- Each candidate includes its numeric score and effort level: e.g., `[Score: 9] [Effort: Medium]`.
- **"Do nothing" is not scored.** The formula applies only to active candidates. "Do nothing" is evaluated via the inaction decision rules. Candidates where inaction is defensible are moved to the "Track Only" section — a separate section below the ranked list, not a low-scoring position within it.

---

## Framework Check Guidance

Guidance for analysis agents performing the framework-native solution check in Phase 3.

### What to Check

Determine whether the project's DI framework, language features, or test framework has built-in patterns that address the friction point. The framework context block (from Phase 0.5) provides framework names and versions. The root cause agent's output (for High-severity findings) provides code-level pattern investigation.

### Evidence Source Tiers

- **Root cause investigation (High-severity):** The root cause agent has already investigated which framework patterns are used vs available in the actual code. Use this as the authoritative source. Tag as `[Root cause investigation (High-severity)]`.
- **Framework hint only (Medium/Low-severity):** No root cause agent was dispatched. The analysis agent works from the Phase 0.5 framework name + version only. Pattern-level usage has NOT been verified against code. Tag as `[Framework hint only (Medium/Low-severity -- pattern usage not verified)]`.

### Applicability Assessment

For each identified framework pattern, assess: would the pattern actually solve the root cause, or just the symptom? A framework pattern that addresses the symptom but not the root cause is still worth noting but should not be presented as a full solution.

---

## Cost of Inaction Criteria

Decision rules for determining whether "do nothing" is a defensible option for a given friction point. Applied by analysis agents in Phase 3.

### Git Metrics Aggregation

When a friction point spans multiple files, the genealogist reports per-file metrics. The orchestrator aggregates them as follows:

- **Headline metric:** The hottest file's change frequency and bug-fix commit count (e.g., "Change frequency: 14 commits/6mo (weekly) -- `src/services/PaymentProcessor.ts`").
- **Range summary:** A one-line range: "Range across N files: [lowest]-[highest] commits/6mo, [lowest]-[highest] bug-fix commits."
- **Inaction rules key on the hottest file.** A single hot file within a friction point's scope makes inaction indefensible — the cost is being paid regardless of whether other files are stable.

### Decision Rules

1. **Defensible — low-activity code:** Modification friction is Low AND hottest file's change frequency is monthly-or-less AND zero bug-fix commits for the hottest file in the analysis window. The code causes friction but nobody is paying the cost frequently enough to justify investment.

2. **Defensible — comprehension-only friction in stable code:** Primary friction dimension is Comprehension (not Modification) AND the hottest file has fewer than 2 modifications per quarter. The code is hard to read but rarely needs to be read.

3. **Not defensible (override):** If the code is blocking known planned work, inaction is never defensible regardless of the above rules.

### Track Only Tier

When inaction is defensible, the finding still proceeds through all analysis steps and appears in candidate selection — but is demoted to a "Track Only" section. This is a separate section below the ranked active candidates, not a low-scoring position within the ranked list. The user can still select a Track Only candidate if they choose.
