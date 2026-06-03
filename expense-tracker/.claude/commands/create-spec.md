--
description: Create a spec file and a feature branch for the next expense tracker step
argument-hint: "Step number and feature name e.g. 2 registration"
allowed-tools: Read, Write, Glob, Bash(git:*)
--

You are a senior developer spinning up a new feature for the 
expense tracker. Alway follow the rule from CLAUDE.md

## Step 1: Check working directory is clean 
Run `git status` check the uncommitted, unstaged or untracked file. If exists
stop immediately and tell the user to commit or stash change before proceeding.
DO NOT CONTINUE untill the working directory is clean.

## Step 2: Parse the argument

From $ARGUMENT extract:
1. `step number`: zero-padded to 2 digits: 2 -> 02, 11 -> 11

2. `feature title`: human readable title in the Title Case
    - Example: "Registration" or "Login and Logout"

3. `feature-slug`: git and file safe slug
    - Lowwercase 
    - Only 0-9, a-z AND -
    - Maximum 40 characters
    - Example: "registration" and "login-logout"

4. `branch-name`: format- `feature/<feature-slug>`

If you can't infer these from the $ARGUMENT then
ask user first before proceeding

## Step 3: Check branch name if already taken
Run `git branch` to list the existing branches:
if branch name is already taken then appen a number:
Example: `feature\<feature-slug>-01`


## Step 4 — Switch to main and pull latest
Run:
```
git checkout main
git pull origin main
```

## Step 5 — Create and switch to the feature branch
Run:
```
git checkout -b <branch_name>
```

## Step 6 — Research the codebase
Read these files before writing the spec:
- `CLAUDE.md` — roadmap, conventions, schema
- `app.py` — existing routes and structure
- `database/db.py` — existing schema and functions
- All files in `.claude/specs/` — avoid duplicating existing specs

Check `CLAUDE.md` to confirm the requested step is not already
marked complete. If it is, warn the user and stop.

## Step 7 — Write the spec
Generate a spec document with this exact structure:

---
# Spec: <feature_title>

## Overview
One paragraph describing what this feature does and why
it exists at this stage of the Spendly roadmap.

## Depends on
Which previous steps this feature requires to be complete.

## Routes
Every new route needed:
- `METHOD /path` — description — access level (public/logged-in)

If no new routes: state "No new routes".

## Database changes
Any new tables, columns, or constraints needed.
Always verify against `database/db.py` before writing this.
If none: state "No database changes".

## Templates
- **Create:** list new templates with their path
- **Modify:** list existing templates and what changes

## Files to change
Every file that will be modified.

## Files to create
Every new file that will be created.

## New dependencies
Any new pip packages. If none: state "No new dependencies".

## Rules for implementation
Specific constraints Claude must follow. Always include:
- No SQLAlchemy or ORMs
- Parameterised queries only
- Passwords hashed with werkzeug
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`

## Definition of done
A specific testable checklist. Each item must be
something that can be verified by running the app.
---

## Step 8 — Save the spec
Save to: `.claude/specs/<step_number>-<feature_slug>.md`

## Step 9 — Report to the user
Print a short summary in this exact format:
```
Branch:    <branch_name>
Spec file: .claude/specs/<step_number>-<feature_slug>.md
Title:     <feature_title>
```

Then tell the user:
"Review the spec at `.claude/specs/<step_number>-<feature_slug>.md`
then enter Plan Mode with Shift+Tab twice to begin implementation."

Do not print the full spec in chat unless explicitly asked.
