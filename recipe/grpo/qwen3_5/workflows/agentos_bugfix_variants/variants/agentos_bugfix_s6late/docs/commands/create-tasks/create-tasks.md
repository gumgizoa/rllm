I want you to prepare the implementation of a new feature from the task description using the following process and instructions.

Carefully carry out the PHASE sections below in order, finishing one before the next.

Instructions to follow in sequence:

# PHASE 1: Initialize the Spec Folder and Study the Change

The FIRST STEP is to create the spec folder. Determine a kebab-case spec name from the task description, then create the folder:

```bash
# Get today's date in YYYY-MM-DD format
TODAY=$(date +%Y-%m-%d)

# Determine kebab-case spec name from the task description
SPEC_NAME="[kebab-case-name]"

# Store this path for output
SPEC_PATH="/tmp/agent-os/specs/${TODAY}-${SPEC_NAME}"

# Create the spec folder and the folder for its verification report
mkdir -p $SPEC_PATH/verifications

echo "Created spec folder: $SPEC_PATH"
```

Then study the change: read the task description in the task message again and explore the code it is about in the repository, until you know what has to change and where.

## Next step

Once you know what has to change and where, open `/agent-os/commands/implement-tasks/implement-tasks.md` and continue with that command. In this run no tasks list is written at this point: `/tmp/agent-os/specs/[this-spec]/tasks.md` is written in implement-tasks PHASE 2, after the change is made.
