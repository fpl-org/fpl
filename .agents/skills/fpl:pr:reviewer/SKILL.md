---
name: fpl:pr:reviewer
description: Ask a login to review an open pull request, with .agents/skills/fpl:pr/scripts/pr --reviewer. Use for a reader beside the maintainer, or to ask him again after a push; CODEOWNERS asks him itself when the pull request leaves draft.
---

    .agents/skills/fpl:pr/scripts/pr --reviewer <number> <login>

The forge asks the code owner the moment a pull request is ready (`fpl:pr:ready`), so this is
for a second reader, or for asking again once a push has answered what he said. Ask him
nothing while the bots still speak, and never on a draft: Ready is his signal.

- **Exit 0**: `pr: asked <login> to review #<n>` on stderr.
- **Exit 1**: the token is not the machine account's, the pull request is not open, or the
  forge refused the login (an author cannot review their own pull request).
