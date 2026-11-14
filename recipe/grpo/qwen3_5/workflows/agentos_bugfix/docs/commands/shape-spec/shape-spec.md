You are helping me shape and plan the scope for a new feature.  The following MULTI-PHASE process is aimed at documenting our key decisions regarding scope, design and architecture approach.

Carefully carry out the PHASE sections below in order, finishing one before the next.

Instructions to follow in sequence:

# PHASE 1: Initialize Spec

The FIRST STEP is to initialize the spec by following these instructions:

# Spec Initialization

## Core Responsibilities

1. **Get the description of the feature:** Take it from the task description in the task message
2. **Initialize Spec Structure**: Create the spec folder with date prefix
3. **Save Raw Idea**: Document the user's exact description without modification
4. **Create Verification Folder**: Set up the folder for this spec's verification report.
5. **Prepare for Requirements**: Set up structure for next phase

## Workflow

### Step 1: Get the description of the feature

You were given a description of the feature: the task description in the task message. Use that to initiate a new spec.

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

echo "Created spec folder: $SPEC_PATH"
```

### Step 3: Create Verification Folder

Create the folder `$SPEC_PATH/verifications/`.

Leave this folder empty, for now.

### Step 4: Save Raw Idea

Write the task description from the task message to `$SPEC_PATH/planning/initialization.md` exactly as given, without modification. PHASE 2 reads the raw idea from this file.

## Important Constraints

- Always use dated folder names (YYYY-MM-DD-spec-name)
- Follow folder structure exactly
- Verification folder should be empty, for now

# PHASE 2: Shape Spec

Now that you've initialized the folder for this new spec, proceed with the research phase.

Follow these instructions for researching this spec's requirements:

# Spec Research

## Core Responsibilities

1. **Read Initial Idea**: Load the raw idea from initialization.md
2. **Ask Clarifying Questions**: Generate targeted questions WITH a reusability check, and answer them yourself
3. **Process Answers**: Analyze responses
4. **Save Requirements**: Document the requirements you've gathered to a single file named: `[spec-path]/planning/requirements.md`

## Workflow

### Step 1: Read Initial Idea

Read the raw idea from `[spec-path]/planning/initialization.md` to understand what the user wants to build.

### Step 2: Generate First Round of Questions WITH Reusability Check

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

**Nobody will answer these questions, so do not send them as a message. Answer each one yourself with the most plausible reading of the task description and the repository, and note the basis of each answer. Answer the reusability question by looking in the repository yourself (Step 3).**

### Step 3: Process Answers

After answering the questions yourself:

1. Store your answers, each with its basis, for later documentation

2. Answer the reusability question by looking in the repository for similar features, components and backend logic:
   - Make note of these paths/names for the write-spec stage to reference
   - Record each as `(assumed) <path> — <basis>`; if you find none, record "No similar existing features identified for reference."

### Step 4: Save Complete Requirements

After all questions are answered, record ALL gathered information to ONE FILE at this location with this name: `[spec-path]/planning/requirements.md`

Use the following structure and do not deviate from this structure when writing your gathered information to `requirements.md`.  Include ONLY the items specified in the following structure:

```markdown
# Spec Requirements: [Spec Name]

## Initial Description
[User's original spec description from initialization.md]

## Requirements Discussion

### First Round Questions

**Q1:** [First question asked]
**Answer:** (assumed) [your answer] — [its basis in the task description or the repository]

**Q2:** [Second question asked]
**Answer:** (assumed) [your answer] — [its basis in the task description or the repository]

[Continue for all questions]

### Existing Code to Reference
[Based on your search of the repository for similar features]

**Similar Features Identified:**
- Feature: [Name] - Path: (assumed) `[path]` — [basis]
- Components to potentially reuse: [what you found]
- Backend logic to reference: [what you found]

[If your search found no similar features]
No similar existing features identified for reference.

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

- DO NOT write technical specifications for development. Just record your findings from information gathering to this single file: `[spec-path]/planning/requirements.md`.
- Ask about existing similar features to promote code reuse
- Record each assumed answer and its basis
- Document paths to similar features for the write-spec stage to reference

## Next step

Once you've completed your research and documented it in `planning/requirements.md`, open `/agent-os/commands/write-spec/write-spec.md` and continue with that command.
