"""
Intelligence gathering components for Ron Clanker.

Monitors external sources for injury news, team news, rotation risks,
and other critical information that provides competitive advantage.
"""

# Core intelligence services (always available)
from .league_intel import LeagueIntelligenceService
from .chip_strategy import ChipStrategyAnalyzer
from .fixture_optimizer import FixtureOptimizer

__all__ = ['LeagueIntelligenceService', 'ChipStrategyAnalyzer', 'FixtureOptimizer']

# Optional monitoring services (require additional dependencies)
try:
    from .website_monitor import WebsiteMonitor
    __all__.append('WebsiteMonitor')
except ImportError:
    pass

try:
    from .rss_monitor import RSSMonitor
    __all__.append('RSSMonitor')
except ImportError:
    pass

try:
    from .youtube_monitor import YouTubeMonitor
    __all__.append('YouTubeMonitor')
except ImportError:
    pass

try:
    from .intelligence_classifier import IntelligenceClassifier
    __all__.append('IntelligenceClassifier')
except ImportError:
    pass
