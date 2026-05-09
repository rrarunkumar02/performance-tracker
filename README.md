# Team Member Training Tracker

Python web app for adding team members and tracking Week 0 to Week 4 training progress-new person.

## Run on your computer

```bash
python3 app.py
```

Open:

```text
http://127.0.0.1:8000
```

## Deploy online

For public hosting with Vercel and Supabase:

1. Run `supabase_schema.sql` in the Supabase SQL Editor.
2. Push this folder to GitHub.
3. Import the GitHub repo into Vercel.
4. Add these Vercel environment variables:

```text
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
```

The service role key must stay server-side in Vercel environment variables. Do not put it inside the code or share it publicly.

For a normal Python server, set the start command to:

```bash
HOST=0.0.0.0 python app.py
```

The app reads the hosting platform's `PORT` environment variable automatically.

## Database

Locally, without Supabase environment variables, the app stores data in:

```text
team_tracker.db
```

Online, with Supabase environment variables, the app stores data in your Supabase tables:

```text
members
member_tracking
```
