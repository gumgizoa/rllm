Resolve this issue by running BMad's Build Auto workflow: one unattended pass that writes a spec, hands
the implementation to a subagent, stages and verifies the diff, and has four review subagents go over it
before the result is recorded.

Your very first action, ahead of any command in the repository, is to read
/bmad-build-auto/core-workflow.md. The directory /bmad-build-auto sits at the filesystem root, next to
/testbed and not inside it, so a search under /testbed turns up nothing. That document sets out the run's
conditions and chains to the four step documents under /bmad-build-auto/stages/.
