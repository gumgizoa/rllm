Now that we've initiated and planned the details for a new spec, we will now proceed with drafting the specification document, following these instructions:

# Spec Writing

## Core Responsibilities

1. **Analyze Requirements**: Load and analyze requirements thoroughly
2. **Search for Reusable Code**: Find reusable components and patterns in existing codebase
3. **Create Specification**: Write comprehensive specification document

## Workflow

### Step 1: Analyze Requirements and Context

Read and understand all inputs and THINK HARD:
```bash
# Read the requirements document
cat /tmp/agent-os/specs/[current-spec]/planning/requirements.md
```

Parse and analyze:
- User's feature description and goals
- Requirements gathered by the shape-spec stage
- Any constraints or out-of-scope items mentioned

### Step 2: Search for Reusable Code

Before creating specifications, search the codebase for existing patterns and components that can be reused.

Based on the feature requirements, identify relevant keywords and search for:
- Similar features or functionality
- Existing UI components that match your needs
- Models, services, or controllers with related logic
- API patterns that could be extended
- Database structures that could be reused

Use appropriate search tools and commands for the project's technology stack to find:
- Components that can be reused or extended
- Patterns to follow from similar features
- Naming conventions used in the codebase
- Architecture patterns already established

Document your findings for use in the specification.

### Step 3: Create Core Specification

Write the main specification to `/tmp/agent-os/specs/[current-spec]/spec.md`.

DO NOT write actual code in the spec.md document. Just describe the requirements clearly and concisely.

Keep it short and include only essential information for each section.

Follow this structure exactly when creating the content of `spec.md`:

```markdown
# Specification: [Feature Name]

## Goal
[1-2 sentences describing the core objective]

## Specific Requirements

**Specific requirement name**
- [Up to 8 CONCISE sub-bullet points to clarify specific sub-requirements, design or architectual decisions that go into this requirement, or the technical approach to take when implementing this requirement]

[repeat for up to a max of 10 specific requirements]

## Existing Code to Leverage

**Code, component, or existing logic found**
- [up to 5 bullets that describe what this existing code does and how it should be re-used or replicated when building this spec]

[repeat for up to 5 existing code areas]

## Out of Scope
- [up to 10 concise descriptions of specific features that are out of scope and MUST NOT be built in this spec]
```

## Important Constraints

1. **Always search for reusable code** before specifying new components
2. **Do NOT write actual code** in the spec
3. **Keep each section short**, with clear, direct, skimmable specifications
4. **Do NOT deviate from the template above** and do not add additional sections

## Next step

Once the spec has been created at `/tmp/agent-os/specs/[this-spec]/spec.md`, open `/agent-os/commands/create-tasks/create-tasks.md` and continue with that command.

## User Standards & Preferences Compliance

IMPORTANT: Ensure that the specification document's content is ALIGNED and DOES NOT CONFLICT with the user's preferences and standards as detailed in the following files:

**`agent-os/standards/global/coding-style.md`**

## Coding style best practices

- **Consistent Naming Conventions**: Establish and follow naming conventions for variables, functions, classes, and files across the codebase
- **Automated Formatting**: Maintain consistent code style (indenting, line breaks, etc.)
- **Meaningful Names**: Choose descriptive names that reveal intent; avoid abbreviations and single-letter variables except in narrow contexts
- **Small, Focused Functions**: Keep functions small and focused on a single task for better readability and testability
- **Consistent Indentation**: Use consistent indentation (spaces or tabs) and configure your editor/linter to enforce it

**`agent-os/standards/global/commenting.md`**

## Code commenting best practices

- **Self-Documenting Code**: Write code that explains itself through clear structure and naming
- **Minimal, helpful comments**: Add concise, minimal comments to explain large sections of code logic.
- **Don't comment changes or fixes**: Do not leave code comments that speak to recent or temporary changes or fixes. Comments should be evergreen informational texts that are relevant far into the future.

**`agent-os/standards/global/conventions.md`**

## General development conventions

- **Consistent Project Structure**: Organize files and directories in a predictable, logical structure that team members can navigate easily
- **Environment Configuration**: Use environment variables for configuration; never commit secrets or API keys to version control

**`agent-os/standards/global/error-handling.md`**

## Error handling best practices

- **User-Friendly Messages**: Provide clear, actionable error messages to users without exposing technical details or security information
- **Fail Fast and Explicitly**: Validate input and check preconditions early; fail with clear error messages rather than allowing invalid state
- **Specific Exception Types**: Use specific exception/error types rather than generic ones to enable targeted handling
- **Centralized Error Handling**: Handle errors at appropriate boundaries (controllers, API layers) rather than scattering try-catch blocks everywhere
- **Graceful Degradation**: Design systems to degrade gracefully when non-critical services fail rather than breaking entirely
- **Retry Strategies**: Implement exponential backoff for transient failures in external service calls
- **Clean Up Resources**: Always clean up resources (file handles, connections) in finally blocks or equivalent mechanisms

**`agent-os/standards/global/validation.md`**

## Validation best practices

- **Validate on Server Side**: Always validate on the server; never trust client-side validation alone for security or data integrity
- **Client-Side for UX**: Use client-side validation to provide immediate user feedback, but duplicate checks server-side
- **Fail Early**: Validate input as early as possible and reject invalid data before processing
- **Specific Error Messages**: Provide clear, field-specific error messages that help users correct their input
- **Allowlists Over Blocklists**: When possible, define what is allowed rather than trying to block everything that's not
- **Type and Format Validation**: Check data types, formats, ranges, and required fields systematically
- **Sanitize Input**: Sanitize user input to prevent injection attacks (SQL, XSS, command injection)
- **Business Rule Validation**: Validate business rules (e.g., sufficient balance, valid dates) at the appropriate application layer
- **Consistent Validation**: Apply validation consistently across all entry points (web forms, API endpoints, background jobs)

**`agent-os/standards/testing/test-writing.md`**

## Test coverage best practices

- **Write Minimal Tests During Development**: Do NOT write tests for every change or intermediate step. Focus on completing the feature implementation first, then add strategic tests only at logical completion points
- **Test Only Core User Flows**: Write tests exclusively for critical paths and primary user workflows. Skip writing tests for non-critical utilities and secondary workflows until if/when you're instructed to do so.
- **Defer Edge Case Testing**: Do NOT test edge cases, error states, or validation logic unless they are business-critical. These can be addressed in dedicated testing phases, not during feature development.
- **Test Behavior, Not Implementation**: Focus tests on what the code does, not how it does it, to reduce brittleness
- **Clear Test Names**: Use descriptive names that explain what's being tested and the expected outcome
- **Mock External Dependencies**: Isolate units by mocking databases, APIs, file systems, and other external services
- **Fast Execution**: Keep unit tests fast (milliseconds) so developers run them frequently during development
