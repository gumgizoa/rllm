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

DO NOT write actual code in the spec.md document, and do not describe the code change in words either (which condition, value or call changes, and to what). Describe the behavior the change must produce: what happens now, what must happen instead and for which inputs, and what must stay as it is. The code change is decided later, during implementation.

Keep it short and include only essential information for each section.

Follow this structure exactly when creating the content of `spec.md`:

```markdown
# Specification: [Feature Name]

## Goal
[1-2 sentences describing the core objective]

## Specific Requirements

**Specific requirement name**
- [Up to 8 CONCISE sub-bullet points to clarify specific sub-requirements: the inputs or situations this requirement covers and the result each must give. No code change and no technical approach]

[repeat for up to a max of 10 specific requirements]

## Existing Code to Leverage

**Code, component, or existing logic found**
- [up to 5 bullets that describe what this existing code does and how it is involved in the behavior to change]

[repeat for up to 5 existing code areas]

## Out of Scope
- [up to 10 concise descriptions of specific features that are out of scope and MUST NOT be built in this spec]
```

## Important Constraints

1. **Always search for reusable code** before specifying new components
2. **Do NOT write actual code** in the spec, **and do not state the code change in words**: the spec says what must hold, not how the code changes
3. **Keep each section short**, with clear, direct, skimmable specifications
4. **Do NOT deviate from the template above** and do not add additional sections

## Next step

Once the spec has been created at `/tmp/agent-os/specs/[this-spec]/spec.md`, open `/agent-os/commands/create-tasks/create-tasks.md` and continue with that command.
