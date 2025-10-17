"""
Intelligence Classifier

Classifies raw intelligence from external sources:
- Assigns confidence scores (0-1) based on language patterns
- Matches player names to FPL IDs using fuzzy matching
- Determines severity (CRITICAL/HIGH/MEDIUM/LOW)
- Decides if intelligence is actionable

Used by Scout agent to process raw intelligence before publishing events.
"""

import logging
import re
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass
from rapidfuzz import fuzz, process

logger = logging.getLogger(__name__)


@dataclass
class ClassifiedIntelligence:
    """Classified intelligence with confidence and severity."""
    player_id: Optional[int]
    player_name: str
    matched_name: Optional[str]  # FPL database name if matched
    confidence: float  # 0-1
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW
    actionable: bool
    match_score: float  # How well did name match (0-100)


class IntelligenceClassifier:
    """
    Classifies and enriches raw intelligence.

    Key responsibilities:
    1. Confidence scoring - analyze language patterns
    2. Player name matching - fuzzy match to FPL database
    3. Severity assessment - determine urgency
    4. Actionability - should Ron act on this?
    """

    # Language patterns for confidence scoring
    HIGH_CONFIDENCE_WORDS = [
        'confirmed', 'official', 'announced', 'definitely',
        'ruled out', 'sidelined', 'suspended', 'banned'
    ]

    MEDIUM_CONFIDENCE_WORDS = [
        'expected', 'likely', 'probably', 'should be',
        'set to', 'looks like'
    ]

    LOW_CONFIDENCE_WORDS = [
        'might', 'could', 'possibly', 'may',
        'rumor', 'speculation', 'unconfirmed'
    ]

    # Severity keywords
    CRITICAL_KEYWORDS = [
        'long-term', 'season', 'months', 'surgery',
        'acl', 'cruciate', 'fracture', 'broken'
    ]

    HIGH_SEVERITY_KEYWORDS = [
        'weeks', 'out for', 'major', 'serious',
        'suspended', 'banned', 'red card'
    ]

    MEDIUM_SEVERITY_KEYWORDS = [
        'doubtful', 'fitness test', 'assessed',
        'rotation', 'rested', 'bench'
    ]

    def __init__(self, player_cache: Dict[str, int] = None):
        """
        Initialize classifier.

        Args:
            player_cache: Dict mapping player names to FPL IDs
        """
        self.player_cache = player_cache or {}

        # Build reverse lookup for fuzzy matching
        self._id_to_name = {v: k for k, v in self.player_cache.items()}

        logger.info(f"IntelligenceClassifier initialized with {len(self.player_cache)} players")

    def classify(
        self,
        raw_intel: Dict[str, Any],
        base_confidence: float = 0.5
    ) -> ClassifiedIntelligence:
        """
        Classify raw intelligence.

        Args:
            raw_intel: Raw intelligence dict from monitor
            base_confidence: Base confidence from source reliability

        Returns:
            ClassifiedIntelligence with scores and matches
        """
        player_name = raw_intel.get('player_name', '')
        details = raw_intel.get('details', '').lower()
        intel_type = raw_intel.get('type', 'INJURY')

        # 1. Adjust confidence based on language
        confidence = self._assess_confidence(details, base_confidence)

        # 2. Match player name to FPL ID
        player_id, matched_name, match_score = self._match_player(player_name)

        # 3. Determine severity
        severity = self._assess_severity(details, intel_type)

        # 4. Decide if actionable
        actionable = self._is_actionable(
            confidence, severity, match_score, intel_type
        )

        return ClassifiedIntelligence(
            player_id=player_id,
            player_name=player_name,
            matched_name=matched_name,
            confidence=confidence,
            severity=severity,
            actionable=actionable,
            match_score=match_score
        )

    def _assess_confidence(self, text: str, base_confidence: float) -> float:
        """
        Assess confidence based on language patterns.

        Args:
            text: Intelligence text (lowercase)
            base_confidence: Starting confidence from source

        Returns:
            Adjusted confidence (0-1)
        """
        confidence = base_confidence

        # Check for high confidence indicators
        if any(word in text for word in self.HIGH_CONFIDENCE_WORDS):
            confidence += 0.2

        # Check for medium confidence indicators
        elif any(word in text for word in self.MEDIUM_CONFIDENCE_WORDS):
            confidence += 0.1

        # Check for low confidence indicators (reduce)
        if any(word in text for word in self.LOW_CONFIDENCE_WORDS):
            confidence -= 0.2

        # Clamp to 0-1 range
        return max(0.0, min(1.0, confidence))

    def _match_player(self, name: str) -> Tuple[Optional[int], Optional[str], float]:
        """
        Match player name to FPL ID using fuzzy matching.

        Args:
            name: Player name from intelligence

        Returns:
            Tuple of (player_id, matched_name, match_score)
        """
        if not name or not self.player_cache:
            return None, None, 0.0

        # Clean name
        clean_name = name.strip().lower()

        # Try exact match first
        if clean_name in self.player_cache:
            player_id = self.player_cache[clean_name]
            return player_id, self._id_to_name[player_id], 100.0

        # Fuzzy match
        all_names = list(self.player_cache.keys())

        # Use rapidfuzz for best match
        result = process.extractOne(
            clean_name,
            all_names,
            scorer=fuzz.token_sort_ratio,
            score_cutoff=60.0  # Minimum 60% match
        )

        if result:
            matched_name, score, _ = result
            player_id = self.player_cache[matched_name]
            original_name = self._id_to_name[player_id]

            logger.debug(f"Matched '{name}' to '{original_name}' (score: {score:.0f})")
            return player_id, original_name, score

        logger.debug(f"Could not match player name: '{name}'")
        return None, None, 0.0

    def _assess_severity(self, text: str, intel_type: str) -> str:
        """
        Assess severity of intelligence.

        Args:
            text: Intelligence text (lowercase)
            intel_type: Type of intelligence

        Returns:
            Severity level: CRITICAL, HIGH, MEDIUM, LOW
        """
        # Critical patterns (long-term injuries, season-ending)
        if any(word in text for word in self.CRITICAL_KEYWORDS):
            return 'CRITICAL'

        # High severity (out for weeks, suspensions)
        if any(word in text for word in self.HIGH_SEVERITY_KEYWORDS):
            return 'HIGH'

        # Medium severity (doubtful, rotation)
        if any(word in text for word in self.MEDIUM_SEVERITY_KEYWORDS):
            return 'MEDIUM'

        # Default based on type
        if intel_type == 'SUSPENSION':
            return 'HIGH'
        elif intel_type == 'INJURY':
            return 'HIGH'  # Assume injury is high unless proven otherwise
        elif intel_type == 'ROTATION':
            return 'MEDIUM'

        return 'MEDIUM'

    def _is_actionable(
        self,
        confidence: float,
        severity: str,
        match_score: float,
        intel_type: str
    ) -> bool:
        """
        Determine if intelligence is actionable.

        Args:
            confidence: Confidence score (0-1)
            severity: Severity level
            match_score: Player name match score (0-100)
            intel_type: Intelligence type

        Returns:
            True if Ron should act on this intelligence
        """
        # Minimum thresholds
        MIN_CONFIDENCE = 0.6
        MIN_MATCH_SCORE = 70.0

        # Must have decent confidence
        if confidence < MIN_CONFIDENCE:
            return False

        # Must match a player (unless lineup leak)
        if match_score < MIN_MATCH_SCORE and intel_type != 'LINEUP_LEAK':
            return False

        # Critical severity is always actionable if above thresholds
        if severity == 'CRITICAL':
            return True

        # High severity requires good confidence + match
        if severity == 'HIGH':
            return confidence >= 0.7 and match_score >= 75.0

        # Medium severity requires higher confidence
        if severity == 'MEDIUM':
            return confidence >= 0.8 and match_score >= 80.0

        # Low severity is rarely actionable
        return False


def test_classifier():
    """Test the intelligence classifier."""
    print("Testing IntelligenceClassifier...\n")

    # Mock player cache
    player_cache = {
        'cole palmer': 123,
        'erling haaland': 456,
        'mohamed salah': 789,
        'bukayo saka': 321,
        'gabriel': 654,
    }

    classifier = IntelligenceClassifier(player_cache)

    # Test cases
    test_cases = [
        {
            'player_name': 'Cole Palmer',
            'details': 'Cole Palmer is confirmed out for six weeks with a knee injury',
            'type': 'INJURY',
            'base_reliability': 0.90
        },
        {
            'player_name': 'Haaland',
            'details': 'Haaland might be rested for the game',
            'type': 'ROTATION',
            'base_reliability': 0.70
        },
        {
            'player_name': 'Gabriel',
            'details': 'Gabriel suspended for three games after red card',
            'type': 'SUSPENSION',
            'base_reliability': 0.95
        },
        {
            'player_name': 'Unknown Player',
            'details': 'Unknown Player is injured',
            'type': 'INJURY',
            'base_reliability': 0.80
        },
    ]

    print("=" * 80)
    for i, test in enumerate(test_cases, 1):
        print(f"\nTest {i}: {test['player_name']}")
        print("-" * 80)
        print(f"Details: {test['details']}")
        print(f"Type: {test['type']}, Base reliability: {test['base_reliability']:.0%}")

        result = classifier.classify(test, test['base_reliability'])

        print(f"\nResults:")
        print(f"  Player ID: {result.player_id}")
        print(f"  Matched Name: {result.matched_name}")
        print(f"  Match Score: {result.match_score:.0f}%")
        print(f"  Confidence: {result.confidence:.0%}")
        print(f"  Severity: {result.severity}")
        print(f"  Actionable: {'✅ YES' if result.actionable else '❌ NO'}")
        print("=" * 80)

    print("\n✅ Classifier test complete!")


if __name__ == '__main__':
    test_classifier()
