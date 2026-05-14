# Team Member Training Tracker

Python web app for adding team members, managing access codes, tracking training progress, and exporting comparison reports.

## Run on your computer

```bash
MASTER_PASSWORD=master123 SESSION_SECRET=test-secret python3 app.py
```

Open:

```text
http://127.0.0.1:8000/login
```

Master/admin page:

```text
http://127.0.0.1:8000/master
```

## Deploy online with Vercel and Supabase

1. Run `supabase_schema.sql` in the Supabase SQL Editor.
2. Push this folder to GitHub.
3. Import or redeploy the GitHub repo in Vercel.
4. Add these Vercel environment variables:

```text
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
MASTER_PASSWORD=choose-a-master-password
SESSION_SECRET=choose-a-long-random-secret
```

Important:

- `SUPABASE_SERVICE_ROLE_KEY` must stay server-side in Vercel environment variables.
- Do not put Supabase keys inside the code.
- The master password is used only at `/master` to create/delete access codes and team members.
- Staff log in at `/login` using access codes created from `/access`.

## Database

Locally, without Supabase environment variables, the app stores data in:

```text
team_tracker.db
```

Online, with Supabase environment variables, the app stores data in:

```text
members
member_tracking
access_users
```
