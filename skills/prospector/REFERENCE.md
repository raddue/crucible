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
