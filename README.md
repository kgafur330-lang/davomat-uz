# DAVOMAT.UZ474

Flask web attendance system with two roles (Super Admin and Admin), PostgreSQL database, CSV reports and Telegram bot.

## Features
- Super Admin: dashboard, create admin accounts, see system-wide student and attendance counts.
- Admin: add students, mark Present/Absent/Late, view daily report, export CSV.
- Telegram bot: student links their Telegram account to Student ID and views latest attendance.
- Shared PostgreSQL database for website and Telegram worker.

## Deploy on Render
1. Upload all files and the `templates/` folder to a new GitHub repository.
2. In Render, create a Blueprint from that repository (it reads `render.yaml`).
3. Set `INITIAL_SUPERADMIN_PASSWORD` and `INITIAL_ADMIN_PASSWORD` to strong unique passwords.
4. Set `BOT_TOKEN` on the `davomat-telegram-bot` worker using the token from BotFather.
5. Wait for both web service and worker to deploy.
6. Open the web service URL and sign in.

Default usernames are `admin` and `operator`. Their initial passwords are the values you set in the Render environment variables. Do not use weak or shared passwords.

## Local run
Set `DATABASE_URL` to a PostgreSQL connection string, then:
`pip install -r requirements.txt`
`python app.py`
In another terminal: `python bot.py`

## Important
- The Telegram bot only shows attendance after the student links their Student ID. Do not share bot tokens.
- This package does not yet implement camera-based face recognition. Face biometrics require a separate consent, security, and deployment design; do not describe this release as Face ID-ready.
- Render plans and database pricing can change. Check the current plan and costs before deploying.
