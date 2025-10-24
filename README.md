# Majda workdays (password protected, persistent last link)

- Adds a simple password gate (password: 2101 hashed) so only authorized users can use the app.
- Upload `.xlsx` or paste a **Google Sheets / Google Drive** link.
- The **last successful link** is saved in `last_link.txt` (server-side) and offered on next visits, across devices.
- Reads the **Směny** sheet (fallback: first sheet). Weekly card-style view with quick jump buttons.
