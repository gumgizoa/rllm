You are helping me shape and plan the scope for a new feature.  The following MULTI-PHASE process is aimed at documenting our key decisions regarding scope, design and architecture approach.

Carefully carry out the PHASE sections below in order, finishing one before the next.

Instructions to follow in sequence:

# PHASE 1: Initialize Spec

The FIRST STEP is to initialize the spec by following these instructions:

# Spec Initialization

## Core Responsibilities

1. **Get the description of the feature:** Take it from the issue in `<issue_description>`
2. **Initialize Spec Structure**: Create the spec folder with date prefix
3. **Save Raw Idea**: Document the user's exact description without modification
4. **Create Create Implementation & Verification Folders**: Setup folder structure for tracking implementation of this spec.
5. **Prepare for Requirements**: Set up structure for next phase

## Workflow

### Step 1: Get the description of the feature

You were given a description of the feature: the issue in `<issue_description>` of the task message. Use that to initiate a new spec.

### Step 2: Initialize Spec Structure

Determine a kebab-case spec name from the user's description, then create the spec folder:

```bash
# Get today's date in YYYY-MM-DD format
TODAY=$(date +%Y-%m-%d)

# Determine kebab-case spec name from user's description
SPEC_NAME="[kebab-case-name]"

# Create dated folder name
DATED_SPEC_NAME="${TODAY}-${SPEC_NAME}"

# Store this path for output
SPEC_PATH="/tmp/agent-os/specs/$DATED_SPEC_NAME"

# Create folder structure following architecture
mkdir -p $SPEC_PATH/planning
mkdir -p $SPEC_PATH/planning/visuals

echo "Created spec folder: $SPEC_PATH"
```

### Step 3: Create Implementation Folder

Create 2 folders:
- `$SPEC_PATH/implementation/`
- `$SPEC_PATH/verifications/`

Leave these folders empty, for now.

### Step 4: Save Raw Idea

Write the issue text from `<issue_description>` to `$SPEC_PATH/planning/initialization.md` exactly as given, without modification. PHASE 2 reads the raw idea from this file.

## Important Constraints

- Always use dated folder names (YYYY-MM-DD-spec-name)
- Follow folder structure exactly
- Implementation folder should be empty, for now

# PHASE 2: Shape Spec

Now that you've initialized the folder for this new spec, proceed with the research phase.

Follow these instructions for researching this spec's requirements:

# Spec Research

## Core Responsibilities

1. **Read Initial Idea**: Load the raw idea from initialization.md
2. **Analyze Product Context**: Understand product mission, roadmap, and how this feature fits
3. **Ask Clarifying Questions**: Generate targeted questions WITH a reusability check, and answer them yourself
4. **Process Answers**: Analyze responses and any provided visuals
5. **Ask Follow-ups**: Based on answers and visual analysis if needed
6. **Save Requirements**: Document the requirements you've gathered to a single file named: `[spec-path]/planning/requirements.md`

## Workflow

### Step 1: Read Initial Idea

Read the raw idea from `[spec-path]/planning/initialization.md` to understand what the user wants to build.

### Step 2: Analyze Product Context

Before generating questions, understand the broader product context. This project has no product documents (mission, roadmap, tech stack), so take that context from the repository itself:

1. **Read Product Mission**: Read the repository's README to understand:
   - The product's overall mission and purpose
   - Target users and their primary use cases
   - Core problems the product aims to solve
   - How users are expected to benefit

2. **Read Product Roadmap**: Read the repository's documentation index (e.g. the table of contents of its `docs/`) to understand:
   - Features and capabilities already completed
   - The current state of the product
   - Where this new feature fits in the broader roadmap
   - Related features that might inform or constrain this work

3. **Read Product Tech Stack**: Read the repository's packaging and build metadata (e.g. `pyproject.toml`, `setup.py`, `setup.cfg`, `package.json`) to understand:
   - Technologies and frameworks in use
   - Technical constraints and capabilities
   - Libraries and tools available

This context will help you:
- Ask more relevant and contextual questions
- Identify existing features that might be reused or referenced
- Ensure the feature aligns with product goals
- Understand user needs and expectations

### Step 3: Generate First Round of Questions WITH Reusability Check

Based on the initial idea, generate 4-8 targeted, NUMBERED questions that explore requirements while suggesting reasonable defaults.

**CRITICAL: Always include the reusability question at the END of your questions.**

**Question generation guidelines:**
- Start each question with a number
- Propose sensible assumptions based on best practices
- Frame questions as "I'm assuming X, is that correct?"
- Make it easy for users to confirm or provide alternatives
- Include specific suggestions they can say yes/no to
- Always end with an open question about exclusions

**Required format:**
```
Based on your idea for [spec name], I have some clarifying questions:

1. I assume [specific assumption]. Is that correct, or [alternative]?
2. I'm thinking [specific approach]. Should we [alternative]?
3. [Continue with numbered questions...]
[Last numbered question about exclusions]

**Existing Code Reuse:**
Are there existing features in your codebase with similar patterns we should reference? For example:
- Similar interface elements or UI components to re-use
- Comparable page layouts or navigation patterns
- Related backend logic or service objects
- Existing models or controllers with similar functionality

Please provide file/folder paths or names of these features if they exist.
```

**Nobody will answer these questions, so do not send them as a message. Answer each one yourself with the most plausible reading of the issue and the repository, and note the basis of each answer. Answer the reusability question by looking in the repository yourself (Step 4).**

### Step 4: Process Answers and MANDATORY Visual Check

After answering the questions yourself:

1. Store your answers, each with its basis, for later documentation

2. **MANDATORY: Check for visual assets regardless of user's response:**

**CRITICAL**: You MUST run the following bash command even if the user says "no visuals" or doesn't mention visuals (Users often add files without mentioning them):

```bash
# List all files in visuals folder - THIS IS MANDATORY
ls -la [spec-path]/planning/visuals/ 2>/dev/null | grep -E '\.(png|jpg|jpeg|gif|svg|pdf)$' || echo "No visual files found"
```

3. IF visual files are found (bash command returns filenames):
   - Use Read tool to analyze EACH visual file found
   - Note key design elements, patterns, and user flows
   - Document observations for each file
   - Check filenames for low-fidelity indicators (lofi, lo-fi, wireframe, sketch, rough, etc.)

4. Answer the reusability question by looking in the repository for similar features, components and backend logic:
   - Make note of these paths/names for the write-spec stage to reference
   - Record each as `(assumed) <path> — <basis>`; if you find none, record "No similar existing features identified for reference."

### Step 5: Generate Follow-up Questions (if needed)

Determine if follow-up questions are needed based on:

**Visual-triggered follow-ups:**
- If visuals were found but user didn't mention them: "I found [filename(s)] in the visuals folder. Let me analyze these for the specification."
- If filenames contain "lofi", "lo-fi", "wireframe", "sketch", or "rough": "I notice you've provided [filename(s)] which appear to be wireframes/low-fidelity mockups. Should we treat these as layout and structure guides rather than exact design specifications, using our application's existing styling instead?"
- If visuals show features not discussed in answers
- If there are discrepancies between answers and visuals

**User's Answers-triggered follow-ups:**
- Vague requirements need clarification
- Missing technical details
- Unclear scope boundaries

**If follow-ups needed, write them down in this format:**
```
Based on your answers [and the visual files I found], I have a few follow-up questions:

1. [Specific follow-up question]
2. [Another follow-up if needed]

Please provide these additional details.
```

**Then answer them yourself the same way, without sending them as a message.**

### Step 6: Save Complete Requirements

After all questions are answered, record ALL gathered information to ONE FILE at this location with this name: `[spec-path]/planning/requirements.md`

Use the following structure and do not deviate from this structure when writing your gathered information to `requirements.md`.  Include ONLY the items specified in the following structure:

```markdown
# Spec Requirements: [Spec Name]

## Initial Description
[User's original spec description from initialization.md]

## Requirements Discussion

### First Round Questions

**Q1:** [First question asked]
**Answer:** (assumed) [your answer] — [its basis in the issue or the repository]

**Q2:** [Second question asked]
**Answer:** (assumed) [your answer] — [its basis in the issue or the repository]

[Continue for all questions]

### Existing Code to Reference
[Based on your search of the repository for similar features]

**Similar Features Identified:**
- Feature: [Name] - Path: (assumed) `[path]` — [basis]
- Components to potentially reuse: [what you found]
- Backend logic to reference: [what you found]

[If your search found no similar features]
No similar existing features identified for reference.

### Follow-up Questions
[If any were asked]

**Follow-up 1:** [Question]
**Answer:** (assumed) [your answer] — [its basis]

## Visual Assets

### Files Provided:
[Based on actual bash check, not user statement]
- `filename.png`: [Description of what it shows from your analysis]
- `filename2.jpg`: [Key elements observed from your analysis]

### Visual Insights:
- [Design patterns identified]
- [User flow implications]
- [UI components shown]
- [Fidelity level: high-fidelity mockup / low-fidelity wireframe]

[If bash check found no files]
No visual assets provided.

## Requirements Summary

### Functional Requirements
- [Core functionality based on answers]
- [User actions enabled]
- [Data to be managed]

### Reusability Opportunities
- (assumed) `[path]` — [Components that might exist already, based on your repository search]
- [Backend patterns to investigate]
- [Similar features to model after]

### Scope Boundaries
**In Scope:**
- [What will be built]

**Out of Scope:**
- [What won't be built]
- [Future enhancements mentioned]

### Technical Considerations
- [Integration points mentioned]
- [Existing system constraints]
- [Technology preferences stated]
- [Similar code patterns to follow]
```

## Important Constraints

- **MANDATORY**: Always run bash command to check visuals folder after answering the questions
- DO NOT write technical specifications for development. Just record your findings from information gathering to this single file: `[spec-path]/planning/requirements.md`.
- Visual check is based on actual file(s) found via bash, NOT user statements
- Check filenames for low-fidelity indicators and clarify design intent if found
- Ask about existing similar features to promote code reuse
- Keep follow-ups minimal (1-3 questions max)
- Record each assumed answer and its basis
- Document all visual findings including fidelity level
- Document paths to similar features for the write-spec stage to reference

## Next step

Once you've completed your research and documented it in `planning/requirements.md`, open `/agent-os/commands/write-spec/write-spec.md` and continue with that command.

## User Standards & Preferences Compliance

IMPORTANT: Ensure that your research questions and insights are ALIGNED and DOES NOT CONFLICT with the user's preferences and standards as detailed in the following files:

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
