# Deployment Guide — Job Matcher

This guide walks you through deploying the Job Matcher app step by step. Follow each section in order. You will use:

- **Supabase** (free): Database, user sign-in, and file storage
- **Railway** (Hobby plan, $5/month): Python API server
- **Vercel** (free): Frontend website
- **GitHub** (free): Code hosting and daily crawl job

---

## Before You Start

- [ ] You have a **GitHub account**
- [ ] Your code is pushed to a **GitHub repository**
- [ ] You have a **credit card** (Railway Hobby plan requires it; Supabase and Vercel free tiers do not)

---

## Part 1: Supabase Setup

Supabase provides the database, user authentication, and file storage.

### Step 1.1: Create a Supabase Project

1. Go to [https://supabase.com](https://supabase.com) and sign in (or create an account).
2. Click **"New Project"**.
3. Fill in:
   - **Name**: `job-matcher` (or any name you like)
   - **Database Password**: Create a strong password and **save it somewhere safe** (you will need it later)
   - **Region**: Choose the closest to you (e.g. Singapore for Asia)
4. Click **"Create new project"**.
5. Wait 1–2 minutes for the project to be ready.

### Step 1.2: Get Your Database Connection String

1. In the Supabase dashboard, click **"Project Settings"** (gear icon in the left sidebar).
2. Click **"Database"** in the left menu.
3. Scroll to **"Connection string"**.
4. Select the **"URI"** tab.
5. Copy the connection string. It looks like:
   ```
   postgresql://postgres.[project-ref]:[YOUR-PASSWORD]@aws-0-[region].pooler.supabase.com:6543/postgres
   ```
6. **Important**: Replace `[YOUR-PASSWORD]` with the database password you created in Step 1.1.
7. Add `?sslmode=require` at the end if it is not already there. Example:
   ```
   postgresql://postgres.xxxxx:YourPassword@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres?sslmode=require
   ```
8. Save this string — you will use it in Railway and GitHub.

### Step 1.3: Run the Database Schema

1. In the Supabase dashboard, click **"SQL Editor"** in the left sidebar.
2. Click **"New query"**.
3. Open the file `scripts/schema.sql` from this project on your computer.
4. Select all the text in that file (Ctrl+A) and copy it.
5. Paste it into the Supabase SQL Editor.
6. Click **"Run"** (or press Ctrl+Enter).
7. You should see a success message. The tables are now created.

### Step 1.4: Create the Resumes Storage Bucket

1. In the Supabase dashboard, click **"Storage"** in the left sidebar.
2. Click **"New bucket"**.
3. Fill in:
   - **Name**: `resumes` (must be exactly this)
   - **Public bucket**: Leave **unchecked** (private)
4. Click **"Create bucket"**.
5. The bucket is ready. The API uses the **service_role** key to upload, which bypasses normal security checks, so no extra policies are needed for basic uploads. If you later get "upload failed" errors, you can add a policy under **Policies** → **New policy** allowing `service_role` to INSERT and UPDATE.

### Step 1.5: Get Supabase API Keys

1. Click **"Project Settings"** (gear icon) → **"API"**.
2. You will see:
   - **Project URL**: e.g. `https://xxxxx.supabase.co` — copy this
   - **anon public** key: long string starting with `eyJ...` — copy this
   - **service_role** key: another long string — copy this (keep it secret; never put it in frontend code)

**JWT verification (new Signing Keys system):** Supabase has migrated from the legacy JWT secret to **JWT Signing Keys**. You do **not** need to copy a JWT secret. The API verifies tokens using the public keys from Supabase’s JWKS endpoint (`https://your-project.supabase.co/auth/v1/.well-known/jwks.json`). As long as you set `SUPABASE_URL`, the API will use this automatically.

**If your project still uses the legacy JWT secret** (older projects): Go to **"JWT Settings"** under API and copy the **"JWT Secret"** value. Set it as `SUPABASE_JWT_SECRET` in Railway. New projects can skip this.

Save these somewhere temporarily:
- Project URL
- anon public key
- service_role key

### Step 1.6: Configure Auth (Optional)

The app uses email+password sign-in. Configure in **Authentication** → **Providers** → **Email**:
- Enable Email provider
- Turn OFF "Confirm email" so users can sign in immediately (no verification link)

Users can self-signup from the app, or you can create them: **Authentication** → **Users** → **Add user** → **Create new user** (enter email and password, share the password with them).

---

## Part 2: Deploy the API on Railway

Railway will host your Python API.

### Step 2.1: Create a Railway Account and Project

1. Go to [https://railway.app](https://railway.app) and sign in with GitHub.
2. Click **"New Project"**.
3. Select **"Deploy from GitHub repo"**.
4. Choose your repository (the one containing this project).
5. If asked, authorize Railway to access your GitHub account.

### Step 2.2: Configure the Service

1. Railway may auto-detect a Dockerfile. You need to tell it to use `Dockerfile.api` (the API, not the frontend).
2. Click on the service that was created.
3. Go to **"Variables"** and add this variable **before** adding the others in Step 2.3:
   - **Name**: `RAILWAY_DOCKERFILE_PATH`
   - **Value**: `Dockerfile.api`
4. This makes Railway build from `Dockerfile.api` instead of the default `Dockerfile`.
5. Under **"Settings"** → **"Networking"**: Generate a domain so your API has a public URL (you will do this in Step 2.4).

### Step 2.3: Add Environment Variables

1. In your Railway service, click **"Variables"** (or **"Environment"**).
2. Click **"Add Variable"** or **"New Variable"** for each of the following. Use **exact** names:

| Variable Name | Value | Where to get it |
|---------------|-------|-----------------|
| `DATABASE_URL` | Your Postgres connection string | From Step 1.2 |
| `SUPABASE_URL` | Your Supabase project URL | From Step 1.5 |
| `SUPABASE_SERVICE_KEY` | Your service_role key | From Step 1.5 |
| `SUPABASE_JWT_SECRET` | *(Optional)* Legacy JWT secret | Only if your project has not migrated to JWT Signing Keys (see Step 1.5) |
| `ALLOWED_ORIGINS` | `https://your-app.vercel.app` (see below) | You will add your Vercel URL here after Part 3 |

3. For now, you can set `ALLOWED_ORIGINS` to `http://localhost:3000` to test locally. After you deploy the frontend (Part 3), come back and add your Vercel URL, e.g.:
   ```
   https://your-app-name.vercel.app
   ```
   If you have multiple origins, separate with commas:
   ```
   https://your-app.vercel.app,http://localhost:3000
   ```

4. Click **"Add"** or **"Save"** for each variable.

### Step 2.4: Deploy and Get the API URL

1. Railway will automatically deploy when you add variables (or click **"Deploy"**).
2. Wait for the build to finish (typically 3–5 minutes). The embedding model downloads on first use, so the first request that needs it (e.g. process resume or matches) may take 30–60 seconds; later requests are fast.
3. Go to **"Settings"** → **"Networking"** → **"Generate Domain"** (or similar).
4. Copy the generated URL, e.g. `https://your-api-name.up.railway.app`. This is your **API URL**.

---

## Part 3: Deploy the Frontend on Vercel

Vercel will host your Next.js website.

### Step 3.1: Create a Vercel Project

1. Go to [https://vercel.com](https://vercel.com) and sign in with GitHub.
2. Click **"Add New..."** → **"Project"**.
3. Import your GitHub repository.
4. Configure the project:
   - **Framework Preset**: Next.js (should be auto-detected)
   - **Root Directory**: `frontend` (important — the frontend code is in the `frontend` folder)
   - **Build Command**: `npm run build` (default)
   - **Output Directory**: `.next` (default)

### Step 3.2: Add Environment Variables

Before deploying, add these variables in Vercel:

1. Click **"Environment Variables"** (or expand that section).
2. Add each variable:

| Variable Name | Value | Where to get it |
|---------------|-------|-----------------|
| `NEXT_PUBLIC_API_URL` | Your Railway API URL | From Step 2.4, e.g. `https://your-api-name.up.railway.app` |
| `NEXT_PUBLIC_SUPABASE_URL` | Your Supabase project URL | From Step 1.5 |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Your Supabase anon public key | From Step 1.5 |

3. Ensure these are set for **Production** (and Preview if you want).

### Step 3.3: Deploy

1. Click **"Deploy"**.
2. Wait for the build to complete.
3. Vercel will give you a URL like `https://your-project.vercel.app`.

### Step 3.4: Update Railway CORS

1. Go back to Railway → your API service → **Variables**.
2. Edit `ALLOWED_ORIGINS` and add your Vercel URL:
   ```
   https://your-project.vercel.app
   ```
   Or if you want both production and local:
   ```
   https://your-project.vercel.app,http://localhost:3000
   ```
3. Save. Railway will redeploy automatically.

---

## Part 4: GitHub Actions (Daily Crawl)

The daily crawl runs automatically every day to fetch new jobs.

### Step 4.1: Add the DATABASE_URL Secret

1. Go to your GitHub repository.
2. Click **"Settings"**.
3. In the left sidebar, click **"Secrets and variables"** → **"Actions"**.
4. Click **"New repository secret"**.
5. **Name**: `DATABASE_URL` (exact, case-sensitive)
6. **Value**: Paste your Supabase Postgres connection string (the same one you used in Railway).
7. Click **"Add secret"**.

### Step 4.1b (Optional): Post-crawl webhook and cache invalidation

The crawl pipeline can call your Vercel app after a crawl to revalidate dashboard and match caches (`incremental_crawl.py` → `POST /api/webhooks/crawl-complete`). That requires **`CRON_SECRET`** (or `REVALIDATE_SECRET`) and a reachable app URL (`CRAWL_WEBHOOK_URL` or `NEXT_PUBLIC_VERCEL_URL`).

The default **Daily Job Crawl** workflow only passes `DATABASE_URL`. It does **not** set these variables, so **scheduled GitHub crawls will not trigger the webhook** unless you add repository secrets and extend the workflow env, for example:

| Secret | Purpose |
|--------|---------|
| `CRON_SECRET` | Same value as in Railway/Vercel; sent as `X-Crawl-Secret` to the webhook |
| `CRAWL_WEBHOOK_URL` | Your production site origin, e.g. `https://your-app.vercel.app` (webhook path is appended in code) |

Without them, invalidate caches manually after crawls if needed (`POST /api/admin/invalidate-pool`, dashboard revalidation routes) or rely on TTLs.

### Step 4.2: Verify the Workflow

1. The workflow file is at `.github/workflows/daily-crawl.yml`.
2. It runs at 02:00 UTC every day (10:00 Singapore time).
3. You can also run it manually: go to **Actions** → **Daily Job Crawl** → **Run workflow**.

### Step 4.3: Test the Crawl

1. Go to **Actions** in your GitHub repo.
2. Click **"Daily Job Crawl"** on the left.
3. Click **"Run workflow"** (dropdown) → **"Run workflow"**.
4. Wait a few minutes. A green checkmark means success.
5. To verify data: in Supabase, go to **SQL Editor** and run:
   ```sql
   SELECT COUNT(*) FROM jobs WHERE is_active = TRUE;
   ```

---

## Verification Checklist

After deployment, verify:

- [ ] Supabase: Tables exist, `resumes` bucket exists, Auth is enabled
- [ ] Railway: API deploys, health check works (visit `https://your-api.up.railway.app/docs`)
- [ ] Vercel: Frontend loads, you can sign in with email+password
- [ ] GitHub: `DATABASE_URL` secret is set, manual workflow run succeeds
- [ ] End-to-end: Sign in → upload resume → see job matches

---

## Troubleshooting

### "CORS error" when using the frontend
- Ensure `ALLOWED_ORIGINS` in Railway includes your exact Vercel URL (with `https://`, no trailing slash).

### "Supabase Storage upload failed"
- Ensure the `resumes` bucket exists and the service role has INSERT/UPDATE policy.
- Check that `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` are correct in Railway.

### "401 Unauthorized" on API calls
- User must be signed in. Ensure email+password auth works and `NEXT_PUBLIC_SUPABASE_*` are set in Vercel.
- Ensure `SUPABASE_URL` is set in Railway (required for JWT verification via JWKS). If using a legacy project, set `SUPABASE_JWT_SECRET` instead.

### Build times out on Railway
- The embedding model is no longer downloaded during build (to avoid timeouts). It downloads on first use. If the build still times out, check your Railway plan: Free = 5 min, Hobby = 20 min. Consider upgrading or simplifying dependencies.

### Daily crawl fails in GitHub Actions
- Check that `DATABASE_URL` secret is set correctly (same as Supabase connection string).
- View the workflow logs in the Actions tab for the exact error.

### No jobs showing
- Run the daily crawl manually once to populate the database.
- Check Supabase SQL: `SELECT COUNT(*) FROM jobs;`

---

## Quick Reference: Where Each Value Goes

| What | Supabase | Railway | Vercel | GitHub Secret |
|------|----------|---------|--------|---------------|
| Postgres connection string | — | `DATABASE_URL` | — | `DATABASE_URL` |
| Supabase URL | — | `SUPABASE_URL` | `NEXT_PUBLIC_SUPABASE_URL` | — |
| Supabase anon key | — | — | `NEXT_PUBLIC_SUPABASE_ANON_KEY` | — |
| Supabase service key | — | `SUPABASE_SERVICE_KEY` | — | — |
| JWT Secret (legacy only) | — | `SUPABASE_JWT_SECRET` *(optional)* | — | — |
| API URL | — | — | `NEXT_PUBLIC_API_URL` | — |
| CORS origins | — | `ALLOWED_ORIGINS` | — | — |

---

## Cost Summary

- **Supabase**: Free tier (500MB database, 1GB storage)
- **Vercel**: Free tier
- **GitHub Actions**: Free (2000 min/month)
- **Railway**: Hobby plan $5/month (required for the API)

**Total: ~$5/month**
