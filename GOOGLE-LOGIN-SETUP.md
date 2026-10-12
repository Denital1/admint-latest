# Google sign-in setup

Create a Google OAuth client of type Web application for this project. Add this exact authorized redirect URI:

    http://127.0.0.1:3000/api/auth/google/callback/

Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in backend/.env, then restart Django. Do not put the secret in frontend files or commit it. If the consent screen is in testing mode, add your Google account as a test user.

Use http://127.0.0.1:3000 consistently for Google sign-in. For another host, update FRONTEND_URL and the authorized redirect URI together. Google OAuth requests only basic profile and email access. Accounts are not automatically merged by matching email; sign in to an existing account before linking a Phantom wallet.

Local database: backend/db.sqlite3. Django stores hashed passwords, user identities, login timestamps and server sessions. No private wallet keys or Google access/refresh tokens are stored.
