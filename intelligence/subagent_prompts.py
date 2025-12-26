#!/usr/bin/env python3
"""
Subagent Prompt Templates for Intelligence Gathering

These prompts are designed for use with Claude Code's Task tool to gather
FPL intelligence without flooding the main conversation context.

CRITICAL PRINCIPLE:
===================
Subagents must be explicitly instructed to DISTRUST their training data
and TRUST only freshly fetched web content. Claude's training data is
outdated for current season information (transfers, injuries, form).

Usage:
------
From Claude Code, spawn a Task with these prompts:

    Task(
        subagent_type="Explore",  # or "general-purpose"
        prompt=INJURY_NEWS_PROMPT.format(gameweek=18)
    )

The subagent will:
1. Use WebSearch/WebFetch to gather current information
2. Extract structured intelligence
3. Return ONLY the summary (not raw content)
4. Trust web sources over its training knowledge
"""

# =============================================================================
# CRITICAL: Training Data Warning
# =============================================================================
# This warning MUST be included in all subagent prompts to prevent the model
# from "correcting" current information based on outdated training data.

TRAINING_DATA_WARNING = """
CRITICAL - TRUST WEB SOURCES, NOT YOUR TRAINING DATA:
======================================================
Your training data is OUTDATED for the current 2025/26 season. Players may have:
- Transferred to different clubs (e.g., a player you "know" plays for Club A may now play for Club B)
- Changed positions
- Been injured/recovered since your training cutoff

When you fetch information from web sources:
1. Report EXACTLY what the source says
2. Do NOT "correct" player teams based on your memory
3. Do NOT question or validate against your training knowledge
4. If a source says "Player X (Team Y) is injured" - report that exactly

The web sources are the TRUTH. Your training data is OUTDATED.
"""

# =============================================================================
# Injury/Availability News Prompt
# =============================================================================

INJURY_NEWS_PROMPT = """
Search for current FPL injury and team news ahead of GW{gameweek}.

{training_warning}

TASK:
1. Use WebSearch to find recent injury news (search terms: "FPL injury news GW{gameweek}", "Premier League injuries December 2025")
2. Use WebFetch on 2-3 of the most relevant results
3. Extract player availability information

RETURN FORMAT (structured, no raw content):

CONFIRMED OUT:
- Player Name (Team): Reason, expected return date

MAJOR DOUBTS (flagged in FPL):
- Player Name (Team): Issue, chance of playing %

RETURNING FROM INJURY:
- Player Name (Team): What they're returning from

SUSPENSIONS:
- Player Name (Team): Reason, games remaining

SOURCES USED:
- List each URL you fetched

Do NOT include any raw webpage content in your response.
Extract and structure only the player availability facts.
""".format(gameweek="{gameweek}", training_warning=TRAINING_DATA_WARNING)


# =============================================================================
# Press Conference Summary Prompt
# =============================================================================

PRESS_CONFERENCE_PROMPT = """
Search for manager press conference summaries ahead of GW{gameweek}.

{training_warning}

TASK:
1. Search for "Premier League press conference GW{gameweek}" or "manager press conference injury update"
2. Focus on the Big 6 + any teams with key FPL assets
3. Extract injury/team news quotes from managers

RETURN FORMAT:

ARSENAL (Manager: [name]):
- [Player]: [Status/Quote]

CHELSEA (Manager: [name]):
- [Player]: [Status/Quote]

[Continue for each team with relevant news]

KEY QUOTES:
- Include direct quotes if available about key players

SOURCES:
- List URLs fetched

Only include teams where you found actual press conference information.
""".format(gameweek="{gameweek}", training_warning=TRAINING_DATA_WARNING)


# =============================================================================
# Captain Picks / Expert Opinion Prompt
# =============================================================================

EXPERT_PICKS_PROMPT = """
Search for FPL expert captain picks and transfer recommendations for GW{gameweek}.

{training_warning}

TASK:
1. Search for "FPL captain picks GW{gameweek}" and "FPL transfer tips GW{gameweek}"
2. Look for content from known FPL experts/sites (FPL Twitter, Fantasy Football Scout, etc.)
3. Aggregate recommendations

RETURN FORMAT:

CAPTAIN PICKS (by frequency):
1. [Player] - mentioned by X sources
2. [Player] - mentioned by Y sources
...

TRANSFER TARGETS (popular ins):
- [Player] (Team) - £Xm - [reason]
- [Player] (Team) - £Xm - [reason]

SELL RECOMMENDATIONS (popular outs):
- [Player] (Team) - [reason]

DIFFERENTIAL PICKS (low ownership, high upside):
- [Player] (Team) - [ownership]% - [reason]

SOURCES:
- List URLs/accounts referenced

Focus on actionable intelligence. Ignore generic advice.
""".format(gameweek="{gameweek}", training_warning=TRAINING_DATA_WARNING)


# =============================================================================
# Fixture Analysis Prompt
# =============================================================================

FIXTURE_ANALYSIS_PROMPT = """
Analyze fixtures for GW{gameweek} to GW{end_gameweek} from an FPL perspective.

{training_warning}

TASK:
1. Search for "FPL fixture analysis GW{gameweek}" or "Premier League fixture difficulty"
2. Identify teams with favorable/unfavorable runs
3. Note any blank gameweeks or double gameweeks

RETURN FORMAT:

BEST FIXTURE RUNS (GW{gameweek}-{end_gameweek}):
1. [Team]: Fixtures: [opponents], FDR: [avg difficulty]
2. [Team]: Fixtures: [opponents], FDR: [avg difficulty]
...

WORST FIXTURE RUNS:
1. [Team]: Fixtures: [opponents], FDR: [avg difficulty]
...

BLANK GAMEWEEKS:
- GW[X]: [Teams with no fixture]

DOUBLE GAMEWEEKS:
- GW[X]: [Teams with 2 fixtures]

KEY FIXTURE SWINGS:
- [Team] fixtures improve from GW[X]
- [Team] fixtures worsen from GW[X]

SOURCES:
- List URLs referenced
""".format(
    gameweek="{gameweek}",
    end_gameweek="{end_gameweek}",
    training_warning=TRAINING_DATA_WARNING
)


# =============================================================================
# YouTube FPL Content Prompt
# =============================================================================

YOUTUBE_FPL_PROMPT = """
Search for recent FPL YouTube content for GW{gameweek} insights.

{training_warning}

TASK:
1. Search for "FPL GW{gameweek} tips" or "[Creator name] GW{gameweek}"
2. Focus on established FPL creators (FPL Mate, Let's Talk FPL, FPL Harry, etc.)
3. Extract key recommendations and insights

Note: You may not be able to access full video transcripts, but video titles
and descriptions often contain key recommendations.

RETURN FORMAT:

VIDEOS FOUND:
1. [Title] by [Creator]
   - Key points from description/title
   - Captain pick if mentioned
   - Transfer suggestions if mentioned

2. [Title] by [Creator]
   ...

AGGREGATED RECOMMENDATIONS:
- Most mentioned captain: [Player]
- Popular transfers in: [Players]
- Popular transfers out: [Players]
- Key tactical insight: [Summary]

SOURCES:
- List video URLs found

If you cannot access video content, report what you can find from titles/descriptions.
""".format(gameweek="{gameweek}", training_warning=TRAINING_DATA_WARNING)


# =============================================================================
# Combined Pre-Deadline Intelligence Prompt
# =============================================================================

PRE_DEADLINE_INTEL_PROMPT = """
Gather comprehensive FPL intelligence ahead of the GW{gameweek} deadline.

{training_warning}

This is a comprehensive search covering multiple intelligence types.

TASK:
1. Search for injury news and press conference updates
2. Search for expert captain picks and transfer recommendations
3. Check for any late team news or lineup leaks

RETURN FORMAT:

=== INJURY/AVAILABILITY UPDATE ===
CONFIRMED OUT:
- [Player (Team)]: [Reason]

MAJOR DOUBTS:
- [Player (Team)]: [Issue, chance %]

RETURNING:
- [Player (Team)]: [Status]

=== EXPERT CONSENSUS ===
TOP CAPTAIN PICKS:
1. [Player] - [sources mentioning]
2. [Player] - [sources mentioning]

HOT TRANSFER TARGETS:
- [Player (Team)] £[price] - [why]

PLAYERS TO SELL:
- [Player (Team)] - [why]

=== LATE NEWS ===
- Any breaking news within last 24 hours

=== SOURCES ===
- [List all URLs fetched]

Keep response focused on actionable intelligence only.
""".format(gameweek="{gameweek}", training_warning=TRAINING_DATA_WARNING)


# =============================================================================
# Helper function to format prompts
# =============================================================================

def get_prompt(prompt_type: str, **kwargs) -> str:
    """
    Get a formatted prompt for subagent intelligence gathering.

    Args:
        prompt_type: One of 'injury', 'press', 'expert', 'fixture', 'youtube', 'full'
        **kwargs: Format arguments (e.g., gameweek=18)

    Returns:
        Formatted prompt string ready for Task tool

    Example:
        prompt = get_prompt('injury', gameweek=18)
        # Then use with Task tool
    """
    prompts = {
        'injury': INJURY_NEWS_PROMPT,
        'press': PRESS_CONFERENCE_PROMPT,
        'expert': EXPERT_PICKS_PROMPT,
        'fixture': FIXTURE_ANALYSIS_PROMPT,
        'youtube': YOUTUBE_FPL_PROMPT,
        'full': PRE_DEADLINE_INTEL_PROMPT,
    }

    if prompt_type not in prompts:
        raise ValueError(f"Unknown prompt type: {prompt_type}. Choose from: {list(prompts.keys())}")

    template = prompts[prompt_type]

    # Apply any provided format arguments
    if kwargs:
        template = template.format(**kwargs)

    return template


# =============================================================================
# Documentation
# =============================================================================

USAGE_DOCUMENTATION = """
Subagent Intelligence Gathering - Usage Guide
==============================================

These prompts are designed for use with Claude Code's Task tool to gather
FPL intelligence efficiently without flooding the main conversation context.

WHY SUBAGENTS?
--------------
1. Raw web content stays in subagent context, not main conversation
2. Only structured summaries return to main conversation
3. Preserves context for actual decision-making
4. Subagents can visit multiple sources without context bloat

CRITICAL: TRAINING DATA TRUST
-----------------------------
All prompts include explicit instructions to:
- TRUST freshly fetched web data
- DISTRUST the model's training knowledge for current season info
- Report what sources say, not what the model "thinks it knows"

This prevents errors like assuming a player is still at their old club
after a mid-season transfer.

EXAMPLE USAGE (from Claude Code):
---------------------------------

# Simple injury news fetch
Task(
    subagent_type="Explore",
    prompt=get_prompt('injury', gameweek=18),
    description="Fetch GW18 injury news"
)

# Comprehensive pre-deadline intelligence
Task(
    subagent_type="general-purpose",
    prompt=get_prompt('full', gameweek=18),
    description="Full GW18 intel sweep"
)

# Fixture analysis for planning
Task(
    subagent_type="Explore",
    prompt=get_prompt('fixture', gameweek=18, end_gameweek=23),
    description="Analyze GW18-23 fixtures"
)

PROMPT TYPES:
-------------
- 'injury':  Current injury/availability news
- 'press':   Manager press conference summaries
- 'expert':  Captain picks and transfer recommendations
- 'fixture': Fixture difficulty analysis
- 'youtube': FPL YouTube creator content
- 'full':    Comprehensive pre-deadline sweep (combines above)

INTEGRATION WITH EXISTING CODE:
-------------------------------
The returned intelligence can be passed to NewsIntelligenceProcessor
for further processing, or stored directly in the database.

See: intelligence/news_processor.py for processing extracted data
See: scripts/gather_news_intelligence.py for automated gathering
"""

if __name__ == "__main__":
    # Print documentation when run directly
    print(USAGE_DOCUMENTATION)
    print("\n" + "="*60)
    print("Example prompt (injury news for GW18):")
    print("="*60)
    print(get_prompt('injury', gameweek=18))
