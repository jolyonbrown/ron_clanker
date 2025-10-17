"""
Intelligence gathering components for Ron Clanker.

Monitors external sources for injury news, team news, rotation risks,
and other critical information that provides competitive advantage.
"""

from .website_monitor import WebsiteMonitor

__all__ = ['WebsiteMonitor']
