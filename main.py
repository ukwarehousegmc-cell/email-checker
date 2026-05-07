#!/usr/bin/env python3
"""
Railway Cron Runner
Runs email_checker.py every day at 3:00 PM UK time (15:00 BST / 14:00 UTC)
"""

import schedule
import time
import logging
import subprocess
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)


def run_check():
    log.info("Running daily email check...")
    result = subprocess.run(
        [sys.executable, "email_checker.py"],
        capture_output=True, text=True
    )
    if result.stdout:
        log.info(result.stdout)
    if result.stderr:
        log.error(result.stderr)
    log.info("Done.")


# 3:00 PM UK time = 14:00 UTC (adjust for BST if needed)
schedule.every().day.at("14:40").do(run_check)

log.info("Scheduler started. Will run daily at 14:00 UTC (3:00 PM UK time).")

# Run once immediately on startup
log.info("Running initial check on startup...")
run_check()

while True:
    schedule.run_pending()
    time.sleep(60)
