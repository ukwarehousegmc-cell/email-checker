# Daily Email Checker — Railway Deployment

Automatically checks Gmail every 24 hours for unreplied emails and sends a digest with Gmail + WhatsApp links.

## Setup Instructions

### Step 1 — GitHub mein upload karo
1. GitHub.com pe new repository banao — name: `email-checker`
2. Ye saari files upload karo

### Step 2 — Railway pe deploy karo
1. Railway.app pe jao → Sign in with GitHub
2. "New Project" → "Deploy from GitHub repo"
3. Apni `email-checker` repo select karo
4. Deploy ho jayegi

### Step 3 — Environment Variables set karo (ZAROORI!)
Railway dashboard mein "Variables" tab mein ye add karo:

| Variable | Value |
|----------|-------|
| `GMAIL_TOKEN_JSON` | (token.json ka poora content paste karo) |
| `NOTIFICATION_EMAIL` | expressmattingsales@gmail.com |
| `WHATSAPP_NUMBER` | 447548740783 |

### GMAIL_TOKEN_JSON kaise set karein?
Apni local `token.json` file kholo, saara content copy karo aur Railway mein paste karo.

## Schedule
- Har roz **3:00 PM UK time** pe chalega
- PC on hone ki zaroorat nahi — Railway 24/7 cloud pe run karti hai
- Completely free tier pe chalega
