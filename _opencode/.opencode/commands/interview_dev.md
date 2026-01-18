---
description: Interview me (as a Developer) to make a spec technically implementation-ready
---
You are interviewing a Developer. On the spec: $1.
gather context from the current repository and use the `question` tool to gather more information.

Your primary goals:
- Remove all ambiguity that would block implementation
- Expose edge cases, failure modes, and tradeoffs
- Define precise behavior, constraints, and interfaces
- Produce a spec that can be directly implemented and tested

Interview focus areas:
- Functional requirements and invariants
- Data models and state transitions
- API contracts, inputs/outputs, and error handling
- Edge cases, invalid states, and recovery behavior
- Performance, scalability, and operational constraints
- Security, privacy, and abuse scenarios
- Explicit non-goals and deferred work
- Testability and acceptance criteria

Rules:
- Be pedantic where ambiguity could cause bugs
- Ask about “what happens if…” scenarios
- Force explicit decisions where multiple implementations are possible
- Prefer explicit constraints over flexibility

Before writing:
- Present a technical outline (requirements → behavior → edge cases → acceptance criteria)
- Ask for confirmation or corrections

Then:
- Overwrite $1 with a developer-grade spec
- Use precise, testable language suitable for tickets and tests
