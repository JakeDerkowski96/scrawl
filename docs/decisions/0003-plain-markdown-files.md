# 0003. One plain Markdown file per note

Status: Accepted

## Context

Notes must be durable, portable, and easy to sync and back up, and the app must stay small.

## Options considered

1. **One `.md` file per note in a folder.**
2. **A single file holding every note.**
3. **SQLite.**

## Decision

One UTF-8 Markdown file per note, with LF newlines, in a user-chosen folder. The filename is a timestamp id that never changes; the title is derived from the first line.

## Consequences

- Notes are readable and editable with any tool, survive the app, and sync with OneDrive for free.
- Renaming files to match titles was rejected: it would fight with the sync client and make external references unstable.
- Search scans every file instead of using an index. Fine for hundreds of small notes, and it cannot go stale when files change outside the app.
- Concurrent edits from two places are last-writer-wins; there is no merge. The app reloads an unmodified note when shown, and never overwrites unsaved typing on reload.
- Deletion is a move to `.trash\`. The only file ever unlinked outright is one that is verifiably blank.
- Only `.md` files are listed. Other files in the folder are left alone.
