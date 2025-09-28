# Architecture Decision Records

This directory contains Architecture Decision Records (ADRs) that document the major architectural choices made in aiogram-sentinel.

## What are ADRs?

Architecture Decision Records (ADRs) are short text files that document important architectural decisions made during the development of a software project. Each ADR describes the context, decision, alternatives considered, and consequences of a specific architectural choice.

## ADR Format

Each ADR follows this structure:

- **Status**: Current status (Proposed, Accepted, Superseded, Deprecated)
- **Date**: When the decision was made
- **Authors**: Who made the decision
- **Context**: The situation that led to the decision
- **Decision**: What was decided
- **Alternatives Considered**: Other options that were evaluated
- **Consequences**: Positive and negative impacts of the decision

## Current ADRs

### [ADR-0001: Middleware Architecture](ADR-0001-middleware-architecture.md)
**Status**: Accepted  
**Date**: 2024-09-28

Establishes the core middleware-based architecture for aiogram-sentinel, including the modular design with separate middleware for each protection feature.

**Key Decisions**:
- Modular middleware components (ThrottlingMiddleware, DebouncingMiddleware, etc.)
- Unified Sentinel interface for configuration
- Protocol-based storage abstraction
- Integration with aiogram's middleware system

### [ADR-0002: Storage Backend Architecture](ADR-0002-storage-backend-architecture.md)
**Status**: Accepted  
**Date**: 2024-09-28

Defines the storage architecture with multiple backend implementations and protocol-based design for extensibility.

**Key Decisions**:
- Protocol-based storage interfaces (RateLimiterBackend, DebounceBackend, etc.)
- Multiple implementations (MemoryStorage, RedisStorage)
- Storage factory pattern for backend creation
- Separation of concerns between different data types

### [ADR-0003: Configuration System Design](ADR-0003-configuration-system-design.md)
**Status**: Accepted  
**Date**: 2024-09-28

Establishes the multi-layered configuration system with global defaults and per-handler overrides.

**Key Decisions**:
- Immutable configuration objects with validation
- Multiple configuration sources with clear precedence
- Handler-specific overrides using decorators
- Environment variable and file-based configuration support

### [ADR-0004: Error Handling Strategy](ADR-0004-error-handling-strategy.md)
**Status**: Accepted  
**Date**: 2024-09-28

Defines the comprehensive error handling strategy focusing on graceful degradation and observability.

**Key Decisions**:
- Defensive error handling with graceful degradation
- Custom exception hierarchy
- Circuit breaker pattern for storage failures
- Structured logging and metrics collection

## How to Use ADRs

### For Developers

When working on aiogram-sentinel:

1. **Read existing ADRs** to understand architectural decisions
2. **Follow established patterns** when implementing new features
3. **Create new ADRs** for significant architectural changes
4. **Update ADRs** when decisions change or evolve

### For Contributors

Before making significant changes:

1. **Review relevant ADRs** to understand the rationale
2. **Discuss alternatives** if you disagree with a decision
3. **Propose new ADRs** for major architectural changes
4. **Update documentation** to reflect any changes

### For Users

ADRs help you understand:

- **Why certain design choices were made**
- **What alternatives were considered**
- **How different components interact**
- **Future direction and evolution**

## Creating New ADRs

### When to Create an ADR

Create an ADR when making decisions about:

- Core architectural patterns
- Technology choices (e.g., storage backends, protocols)
- API design decisions
- Performance vs. maintainability tradeoffs
- Security and privacy considerations

### ADR Template

Use this template for new ADRs:

```markdown
# ADR-XXXX: Title

**Status**: Proposed/Accepted/Superseded/Deprecated
**Date**: YYYY-MM-DD
**Authors**: Name(s)

## Context

Describe the situation that led to this decision. What problem are we trying to solve?

## Decision

What was decided? Be specific and actionable.

## Alternatives Considered

What other options were evaluated? Why were they rejected?

### Alternative 1: Description
**Pros**: List benefits
**Cons**: List drawbacks
**Rejected**: Why this wasn't chosen

## Consequences

### Positive
- List positive impacts

### Negative
- List negative impacts

### Risks
- List potential risks

## Implementation Details

Technical details about how the decision will be implemented.

## Success Metrics

How will we measure if this decision was successful?

## References

Links to relevant documentation, discussions, or external resources.

## Related ADRs

Link to other ADRs that are related to this decision.
```

### ADR Numbering

ADRs are numbered sequentially starting from 0001. Use the next available number when creating a new ADR.

### ADR Lifecycle

1. **Proposed**: Initial draft, under discussion
2. **Accepted**: Decision has been made and approved
3. **Superseded**: Replaced by a newer ADR
4. **Deprecated**: No longer relevant or applicable

## Historical Context

### Design Philosophy

aiogram-sentinel follows these architectural principles:

- **Modularity**: Components should be independently usable
- **Extensibility**: Easy to add new features and storage backends
- **Performance**: Minimal overhead in the critical path
- **Type Safety**: Full type annotations for better developer experience
- **Reliability**: Graceful degradation and error handling

### Evolution

The architecture has evolved through these phases:

1. **Initial Design** (ADR-0001): Core middleware architecture
2. **Storage Abstraction** (ADR-0002): Protocol-based storage backends
3. **Configuration System** (ADR-0003): Flexible configuration with overrides
4. **Error Handling** (ADR-0004): Comprehensive error handling strategy

## Future ADRs

Upcoming architectural decisions may include:

- **ADR-0005**: Key Generation and Security
- **ADR-0006**: Performance Optimization Strategies
- **ADR-0007**: Distributed Architecture
- **ADR-0008**: Plugin and Extension System
- **ADR-0009**: Metrics and Observability
- **ADR-0010**: Testing and Quality Assurance

## Questions and Feedback

If you have questions about any ADR or want to discuss architectural decisions:

- Open an issue on [GitHub](https://github.com/ArmanAvanesyan/aiogram-sentinel/issues)
- Start a discussion in [GitHub Discussions](https://github.com/ArmanAvanesyan/aiogram-sentinel/discussions)
- Contact the maintainers directly

## Contributing to ADRs

We welcome contributions to improve existing ADRs or propose new ones:

1. **Fork the repository**
2. **Create a new branch** for your ADR
3. **Write the ADR** following the template
4. **Submit a pull request** for review
5. **Discuss and iterate** based on feedback

Remember that ADRs document decisions, not requirements. They should explain the reasoning behind choices to help future developers understand the codebase.
