#!/usr/bin/env python3
"""Manual GW13 announcement - overriding broken ML predictions"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.notifications import NotificationManager

announcement = """**GAMEWEEK 13 - RON'S PICKS (MANUAL OVERRIDE)**

Right lads. Listen up.

The computers have gone daft this week. They're telling me to bench Haaland at home to Leeds and start some nobody called Woltemade. Absolute nonsense.

Let me spell this out:
- Haaland: £14.9m, 14 goals in 12 games
- Playing AT HOME
- Against LEEDS (bottom 3, can't defend)
- This is the fixture you BUY Haaland for

So I'm overriding the system. Old school football management.

**THE TEAM:**

**GK:** Roefs

**DEFENCE:** Guéhi (VC), Senesi, Richards, Chalobah
Solid back four. Palace playing well defensively.

**MIDFIELD:** Semenyo, Sarr, Cullen, Ndiaye
Work rate. Graft. Points from defensive contribution.

**ATTACK:** Haaland (TC), João Pedro
Here's where it gets interesting.

**TRIPLE CAPTAIN: HAALAND**

That's right. All 8 chips still unused. If you can't triple captain Haaland at home to Leeds, when CAN you use it?

Man City vs a team that's conceded 30+ goals and looks relegated already. This is as close to a guarantee as you get in football.

The ML model's broken - it's got Haaland at 2.8 points. That's laughable. Sometimes you trust the fundamentals over the spreadsheet.

**NO TRANSFERS** - Banking the free transfer for next week.

**Bench:** Pope, Virgil, Garner, Thiago

The computers will get fixed for next week. This week, we're backing the best striker in the league at home to a Championship-level defence.

Fortune favours the brave. And the sensible.

- Ron"""

if __name__ == "__main__":
    notifier = NotificationManager()
    result = notifier.send_notification(announcement, title="GW13 Team Selection")
    if result:
        print("✓ Announcement posted to Slack")
    else:
        print("⚠️  No webhook configured")

    # Also save to file
    with open('data/ron_gw13_announcement.txt', 'w') as f:
        f.write(announcement)
    print("✓ Announcement saved to data/ron_gw13_announcement.txt")
