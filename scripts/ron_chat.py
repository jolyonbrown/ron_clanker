#!/usr/bin/env python3
"""
Chat with Ron at the terminal.

The Slack chat bot (ron_clanker/slack_bot.py) needs workspace app
tokens we don't currently have rights to create. This is the SAME
brain — same persona, same intent classifier, same safety rails, same
read-only context — over stdin/stdout instead of Socket Mode. Needs
only ANTHROPIC_API_KEY.

Usage:
    venv/bin/python scripts/ron_chat.py
    > captain Salah this week please
    RON: Not your call, son. ...
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data.database import Database
from ron_clanker.slack_bot import RateLimiter, RonSlackBot


def main():
    try:
        bot = RonSlackBot(
            database=Database(),
            # generous local limits — it's your own API budget
            limiter=RateLimiter(per_user_per_minute=30, daily_budget=500),
        )
    except Exception as e:
        sys.exit(f"Couldn't start (ANTHROPIC_API_KEY set?): {e}")

    print("Ron Clanker is listening. Ctrl-D or 'quit' to leave him to it.\n")
    while True:
        try:
            msg = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not msg:
            continue
        if msg.lower() in ('quit', 'exit'):
            break
        reply = bot.handle(msg, user='terminal')
        print(f"\nRON: {reply or '(Ron has nothing to say to that.)'}\n")


if __name__ == '__main__':
    main()
