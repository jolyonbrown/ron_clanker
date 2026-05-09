"""
FPL API Submission Service

Authenticates with the FPL website and submits team changes:
- Transfers (in/out)
- Captain / vice-captain
- Bench order (positions 12-15)
- Chip activation (wildcard, freehit, bboost, 3xc)

Authentication uses Playwright to drive headless Chromium through the
PingOne DaVinci OIDC flow, then extracts the access token for API calls.

Safety features:
- Dry-run mode (log what WOULD happen, don't submit)
- Pre-submission validation against FPL rules
- Detailed logging of all API interactions
- Slack notification on success/failure
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import sys

import requests

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data.database import Database
from utils.config import load_config

logger = logging.getLogger('ron_clanker.fpl_submission')

FPL_BASE_URL = "https://fantasy.premierleague.com/api"
FPL_REFERER = "https://fantasy.premierleague.com/"
CHROMIUM_PATH = "/usr/bin/chromium"
# Persistent browser state so we don't re-login every time
BROWSER_STATE_DIR = project_root / 'data' / '.browser_state'

# Chip name mapping: internal name -> FPL API chip value
CHIP_API_MAP = {
    'wildcard': 'wildcard',
    'freehit': 'freehit',
    'bboost': 'bboost',
    'bench_boost': 'bboost',
    '3xc': '3xc',
    'triple_captain': '3xc',
}


@dataclass
class SubmissionResult:
    """Result of an FPL submission attempt."""
    success: bool
    action: str  # 'transfers', 'team', 'chip', 'full'
    gameweek: int
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    dry_run: bool = False


class FPLSubmissionClient:
    """
    Authenticated FPL API client for submitting team changes.

    Usage:
        client = FPLSubmissionClient()
        client.login()

        # Submit transfers
        client.submit_transfers(gameweek=32, transfers=[...])

        # Set team (captain, bench order)
        client.submit_team(gameweek=32, picks=[...])

        # Or do everything from the draft_team table
        client.submit_gameweek_from_draft(gameweek=32)
    """

    def __init__(self, dry_run: bool = False):
        self.session = requests.Session()
        self.authenticated = False
        self.dry_run = dry_run
        self.team_id = None
        self.access_token = None

        config = load_config()
        self.team_id = config.get('team_id')
        self.email = os.getenv('FPL_USER_NAME', '') or os.getenv('FPL_EMAIL', '')
        self.password = os.getenv('FPL_PASSWORD', '')

        self.session.headers.update({
            'User-Agent': (
                'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
                '(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
            ),
            'Accept': 'application/json',
            'Accept-Language': 'en-GB,en;q=0.9',
            'Origin': 'https://fantasy.premierleague.com',
            'Referer': FPL_REFERER,
        })

        if dry_run:
            logger.info("FPL Submission Client initialized in DRY RUN mode")

    def login(self) -> bool:
        """
        Authenticate with FPL via headless Chromium.

        Uses Playwright to drive through the PingOne DaVinci OIDC flow,
        then extracts cookies and access token for API calls.
        Persists browser state to avoid re-login on subsequent runs.

        Returns:
            True if login successful
        """
        if not self.email or not self.password:
            logger.error("FPL credentials not configured. Set FPL_USER_NAME and FPL_PASSWORD in .env")
            return False

        if not self.team_id:
            logger.error("FPL team ID not configured. Set FPL_TEAM_ID in .env")
            return False

        logger.info(f"Logging in to FPL as {self.email}...")

        # Try to reuse existing browser state first
        if self._try_restore_session():
            return True

        # Full login via headless browser
        return self._login_via_browser()

    def _try_restore_session(self) -> bool:
        """Try to restore a previous session from saved browser state."""
        state_file = BROWSER_STATE_DIR / 'session.json'
        if not state_file.exists():
            return False

        try:
            state = json.loads(state_file.read_text())
            cookies = state.get('cookies', [])
            token = state.get('access_token')

            if not token:
                return False

            # Set cookies on our requests session
            for cookie in cookies:
                self.session.cookies.set(
                    cookie['name'], cookie['value'],
                    domain=cookie.get('domain', '.premierleague.com'),
                    path=cookie.get('path', '/'),
                )
            self.access_token = token

            # Test if the session is still valid
            resp = self.session.get(
                f"{FPL_BASE_URL}/me/",
                headers=self._authed_headers(),
                timeout=10,
            )

            if resp.status_code == 200:
                data = resp.json()
                if data.get('player', {}).get('entry'):
                    logger.info("Restored existing FPL session")
                    self.authenticated = True
                    return True

            logger.info("Saved session expired, doing full login")
            return False

        except Exception as e:
            logger.debug(f"Could not restore session: {e}")
            return False

    def _login_via_browser(self) -> bool:
        """
        Full login via headless Chromium + Playwright.

        Flow:
        1. Navigate to fantasy.premierleague.com
        2. Accept cookie consent
        3. Click "Log in" button (triggers OIDC redirect to account.premierleague.com)
        4. Fill email + password on PingOne DaVinci login form
        5. Click "Sign in" and wait for redirect back to FPL
        6. Extract access token from localStorage (OIDC user storage)
        7. Save session for reuse
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error("Playwright not installed. Run: pip install playwright")
            return False

        BROWSER_STATE_DIR.mkdir(parents=True, exist_ok=True)
        OIDC_STORAGE_KEY = (
            'oidc.user:https://account.premierleague.com/as:'
            'bfcbaf69-aade-4c1b-8f00-c1cb8a193030'
        )

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    executable_path=CHROMIUM_PATH,
                )
                context = browser.new_context(
                    user_agent=(
                        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
                        '(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
                    ),
                )
                page = context.new_page()

                # Step 1: Navigate to FPL homepage
                logger.info("Navigating to FPL...")
                page.goto('https://fantasy.premierleague.com/', timeout=30000)
                page.wait_for_timeout(5000)

                # Step 2: Accept cookie consent if present
                accept_btn = page.locator('#onetrust-accept-btn-handler')
                if accept_btn.count() > 0:
                    accept_btn.click()
                    page.wait_for_timeout(2000)

                # Step 3: Click "Log in" button (triggers OIDC redirect)
                logger.info("Clicking Log in...")
                login_btn = page.locator('button:has-text("Log in")')
                with page.expect_navigation(timeout=30000, wait_until='load'):
                    login_btn.click()
                page.wait_for_timeout(5000)

                # Step 4: Fill credentials on PingOne login form
                logger.info("Entering credentials...")
                username_field = page.locator('#username')
                password_field = page.locator('#password')

                username_field.wait_for(state='visible', timeout=15000)
                username_field.fill(self.email)
                password_field.fill(self.password)

                # Step 5: Click "Sign in"
                submit_btns = page.locator(
                    'button[type="submit"], '
                    'button:has-text("Sign in"), '
                    'button:has-text("Sign In")'
                )
                for i in range(submit_btns.count()):
                    btn = submit_btns.nth(i)
                    if btn.is_visible():
                        btn.click()
                        break

                # Wait for redirect back to FPL
                logger.info("Waiting for authentication...")
                page.wait_for_url(
                    'https://fantasy.premierleague.com/**',
                    timeout=30000,
                )
                page.wait_for_timeout(3000)

                # Step 6: Extract access token from OIDC storage
                oidc_data = page.evaluate(
                    f'window.localStorage.getItem("{OIDC_STORAGE_KEY}")'
                )

                token = None
                if oidc_data:
                    try:
                        parsed = json.loads(oidc_data)
                        token = parsed.get('access_token')
                    except (json.JSONDecodeError, TypeError):
                        pass

                # Extract cookies
                cookies = context.cookies()
                browser.close()

                if not token:
                    logger.error("Login redirected but no access token found")
                    return False

                # Set up requests session
                self.access_token = token
                for cookie in cookies:
                    self.session.cookies.set(
                        cookie['name'], cookie['value'],
                        domain=cookie.get('domain', '.premierleague.com'),
                        path=cookie.get('path', '/'),
                    )

                self.authenticated = True
                self._save_session(cookies, token)
                logger.info("FPL login successful via headless browser")
                return True

        except Exception as e:
            logger.error(f"Headless browser login failed: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return False

    def _save_session(self, cookies: list, token: Optional[str]):
        """Persist session state for reuse."""
        state = {
            'cookies': [
                {
                    'name': c['name'],
                    'value': c['value'],
                    'domain': c.get('domain', ''),
                    'path': c.get('path', '/'),
                }
                for c in cookies
            ],
            'access_token': token,
            'saved_at': time.time(),
        }
        state_file = BROWSER_STATE_DIR / 'session.json'
        state_file.write_text(json.dumps(state))
        logger.debug("Session state saved")

    def _authed_headers(self) -> Dict[str, str]:
        """Get headers required for authenticated requests."""
        headers = {
            'Content-Type': 'application/json',
            'Referer': FPL_REFERER,
        }
        # Use Bearer token if available (new OIDC flow)
        if self.access_token:
            headers['Authorization'] = f'Bearer {self.access_token}'
        # Also include CSRF token from cookies if present
        csrf = self.session.cookies.get('csrftoken', '')
        if csrf:
            headers['X-CSRFToken'] = csrf
        return headers

    def get_my_team(self) -> Optional[Dict]:
        """
        Fetch current team state from FPL API (authenticated).

        Returns the live team as FPL sees it - picks, chips, transfers info.
        """
        if not self.authenticated:
            logger.error("Not authenticated - call login() first")
            return None

        url = f"{FPL_BASE_URL}/my-team/{self.team_id}/"
        try:
            resp = self.session.get(url, headers=self._authed_headers(), timeout=15)
            if resp.status_code == 200:
                return resp.json()
            else:
                logger.error(f"GET my-team failed: {resp.status_code} - {resp.text[:300]}")
                return None
        except Exception as e:
            logger.error(f"GET my-team request failed: {e}")
            return None

    def submit_transfers(
        self,
        gameweek: int,
        transfers: List[Dict],
        chip: Optional[str] = None,
    ) -> SubmissionResult:
        """
        Submit transfers to FPL.

        Args:
            gameweek: Target gameweek number
            transfers: List of dicts with keys:
                - element_in: player ID being transferred in
                - element_out: player ID being transferred out
                - purchase_price: cost of incoming player (in tenths, e.g. 55 = 5.5m)
                - selling_price: sale price of outgoing player (in tenths)
            chip: Optional chip to activate ('wildcard', 'freehit', or None)

        Returns:
            SubmissionResult with success status and details
        """
        if not self.authenticated:
            return SubmissionResult(
                success=False, action='transfers', gameweek=gameweek,
                message="Not authenticated"
            )

        if not transfers:
            logger.info("No transfers to submit")
            return SubmissionResult(
                success=True, action='transfers', gameweek=gameweek,
                message="No transfers needed"
            )

        # Build the transfer payload
        transfer_list = []
        for t in transfers:
            transfer_list.append({
                'element_in': t['element_in'],
                'element_out': t['element_out'],
                'purchase_price': t['purchase_price'],
                'selling_price': t['selling_price'],
            })

        # FPL's /transfers/ endpoint activates transfer chips via the
        # `chip` string field, NOT the `wildcard: bool` / `freehit: bool`
        # flags (those are silently ignored by the current API). Verified
        # live on 2026-04-24: `wildcard: true` → 9 transfers recorded as
        # regular with -4 hit; `chip: 'wildcard'` → chip status_for_entry
        # flipped to 'active' and transfers.made reset to 0.
        payload = {
            'confirmed': True,
            'entry': self.team_id,
            'event': gameweek,
            'transfers': transfer_list,
            'chip': chip if chip in ('wildcard', 'freehit') else None,
        }

        transfer_summary = ", ".join(
            f"OUT:{t['element_out']}->IN:{t['element_in']}" for t in transfer_list
        )
        logger.info(f"Submitting {len(transfer_list)} transfer(s) for GW{gameweek}: {transfer_summary}")

        if self.dry_run:
            logger.info(f"DRY RUN - would POST to /api/transfers/: {payload}")
            return SubmissionResult(
                success=True, action='transfers', gameweek=gameweek,
                message=f"DRY RUN: {len(transfer_list)} transfer(s) prepared",
                details={'payload': payload}, dry_run=True
            )

        url = f"{FPL_BASE_URL}/transfers/"
        try:
            resp = self.session.post(
                url,
                json=payload,
                headers=self._authed_headers(),
                timeout=30,
            )

            if resp.status_code == 200:
                logger.info(f"Transfers submitted successfully for GW{gameweek}")
                return SubmissionResult(
                    success=True, action='transfers', gameweek=gameweek,
                    message=f"{len(transfer_list)} transfer(s) confirmed",
                    details={'response': resp.json() if resp.text else {}}
                )
            else:
                error_text = resp.text[:500]
                logger.error(f"Transfer submission failed: {resp.status_code} - {error_text}")
                return SubmissionResult(
                    success=False, action='transfers', gameweek=gameweek,
                    message=f"FPL API returned {resp.status_code}: {error_text}",
                    details={'status_code': resp.status_code}
                )
        except Exception as e:
            logger.error(f"Transfer submission request failed: {e}")
            return SubmissionResult(
                success=False, action='transfers', gameweek=gameweek,
                message=f"Request failed: {e}"
            )

    def submit_team(
        self,
        picks: List[Dict],
        chip: Optional[str] = None,
    ) -> SubmissionResult:
        """
        Submit team selection (captain, vice-captain, bench order).

        Args:
            picks: List of 15 dicts with keys:
                - element: player ID
                - position: 1-15 (1-11 starting, 12-15 bench)
                - is_captain: bool
                - is_vice_captain: bool
            chip: Optional chip to activate ('bboost', '3xc', or None)
                  Note: wildcard/freehit are submitted via transfers endpoint

        Returns:
            SubmissionResult with success status
        """
        if not self.authenticated:
            return SubmissionResult(
                success=False, action='team', gameweek=0,
                message="Not authenticated"
            )

        # Validate picks
        if len(picks) != 15:
            return SubmissionResult(
                success=False, action='team', gameweek=0,
                message=f"Expected 15 picks, got {len(picks)}"
            )

        captain_count = sum(1 for p in picks if p.get('is_captain'))
        vc_count = sum(1 for p in picks if p.get('is_vice_captain'))
        if captain_count != 1 or vc_count != 1:
            return SubmissionResult(
                success=False, action='team', gameweek=0,
                message=f"Need exactly 1 captain and 1 vice-captain (got {captain_count}C, {vc_count}VC)"
            )

        # Map chip name if needed
        api_chip = CHIP_API_MAP.get(chip) if chip else None

        payload = {
            'chip': api_chip,
            'picks': [
                {
                    'element': p['element'],
                    'position': p['position'],
                    'is_captain': p.get('is_captain', False),
                    'is_vice_captain': p.get('is_vice_captain', False),
                }
                for p in sorted(picks, key=lambda x: x['position'])
            ]
        }

        captain = next((p for p in picks if p.get('is_captain')), None)
        logger.info(f"Submitting team: captain={captain['element'] if captain else '?'}, chip={api_chip}")

        if self.dry_run:
            logger.info(f"DRY RUN - would POST to /api/my-team/{self.team_id}/: {payload}")
            return SubmissionResult(
                success=True, action='team', gameweek=0,
                message="DRY RUN: Team selection prepared",
                details={'payload': payload}, dry_run=True
            )

        url = f"{FPL_BASE_URL}/my-team/{self.team_id}/"
        try:
            resp = self.session.post(
                url,
                json=payload,
                headers=self._authed_headers(),
                timeout=30,
            )

            if resp.status_code == 200:
                logger.info("Team selection submitted successfully")
                return SubmissionResult(
                    success=True, action='team', gameweek=0,
                    message="Team selection confirmed",
                    details={'response': resp.json() if resp.text else {}}
                )
            else:
                error_text = resp.text[:500]
                logger.error(f"Team submission failed: {resp.status_code} - {error_text}")
                return SubmissionResult(
                    success=False, action='team', gameweek=0,
                    message=f"FPL API returned {resp.status_code}: {error_text}",
                    details={'status_code': resp.status_code}
                )
        except Exception as e:
            logger.error(f"Team submission request failed: {e}")
            return SubmissionResult(
                success=False, action='team', gameweek=0,
                message=f"Request failed: {e}"
            )

    def submit_gameweek_from_draft(self, gameweek: int) -> SubmissionResult:
        """
        Submit the full gameweek from draft_team and draft_transfers tables.

        This is the main entry point for autonomous operation:
        1. Reads draft_transfers -> submits transfers to FPL
        2. Reads draft_team -> submits team selection (captain, bench order)

        Args:
            gameweek: Target gameweek

        Returns:
            SubmissionResult for the overall operation
        """
        db = Database()
        results = []

        # --- Step 1: Get current team from FPL to understand state ---
        logger.info(f"=== SUBMITTING GW{gameweek} FROM DRAFT ===")

        my_team = self.get_my_team()
        if my_team is None:
            return SubmissionResult(
                success=False, action='full', gameweek=gameweek,
                message="Could not fetch current team from FPL"
            )

        current_picks = {p['element'] for p in my_team.get('picks', [])}
        # FPL's /my-team/ response carries the authoritative selling_price
        # per player — use it so transfer submissions don't fail with
        # "Selling price for element_out has changed" when our local
        # current_team table is stale.
        fpl_selling_price = {
            p['element']: p.get('selling_price', 0)
            for p in my_team.get('picks', [])
        }
        logger.info(f"Current FPL team has {len(current_picks)} players")

        # --- Step 2: Submit transfers ---
        draft_transfers = db.get_draft_transfers(gameweek)
        draft_team = db.get_draft_team(gameweek)

        if not draft_team:
            return SubmissionResult(
                success=False, action='full', gameweek=gameweek,
                message=f"No draft team found for GW{gameweek}"
            )

        # Determine chip usage from draft
        chip_used = self._detect_chip_from_draft(db, gameweek)

        # If no draft_transfers, check the transfers table for this GW
        # (the manager agent stores transfers there, not in draft_transfers)
        if not draft_transfers:
            draft_transfers = db.execute_query("""
                SELECT player_out_id, player_in_id
                FROM transfers
                WHERE gameweek = ?
                ORDER BY id DESC
            """, (gameweek,))

        # Figure out which transfers actually need submitting by comparing
        # draft team vs current FPL team
        draft_player_ids = {p['player_id'] for p in draft_team}
        new_players = draft_player_ids - current_picks
        removed_players = current_picks - draft_player_ids

        if new_players:
            # FPL's /transfers/ endpoint validates that every (element_in,
            # element_out) pair is the same element_type regardless of the
            # wildcard/freehit flag. A full rebuild can only be submitted
            # if each incoming player is paired with an outgoing player of
            # the same position. So we load element_types up-front and
            # pair accordingly. The previous implementation used an
            # arbitrary set.pop() which produced type-mismatch 400s on
            # every wildcard play.
            from collections import defaultdict
            involved_ids = list(new_players | removed_players)
            player_type: Dict[int, int] = {}
            if involved_ids:
                placeholders = ','.join('?' * len(involved_ids))
                type_rows = db.execute_query(
                    f"SELECT id, element_type FROM players WHERE id IN ({placeholders})",
                    tuple(involved_ids)
                )
                player_type = {r['id']: r['element_type'] for r in type_rows}

            # Group removed players by position type for type-matched pairing
            removed_by_type: Dict[int, List[int]] = defaultdict(list)
            for pid in removed_players:
                et = player_type.get(pid)
                if et is not None:
                    removed_by_type[et].append(pid)

            # For full rebuilds (WC/FH) the manager does not write explicit
            # transfer pairs, and any stale rows in the transfers table
            # from an earlier run would mis-pair. Skip the explicit-pair
            # lookup entirely when a rebuild chip is active.
            skip_explicit_pairs = chip_used in ('wildcard', 'freehit')

            transfers_for_api = []
            # Track outs already paired to prevent double-use across the
            # explicit-pair branch and the type-matched fallback. Without
            # this, an out player could be popped by the fallback for one
            # in_id, then matched again by an explicit pair for another
            # in_id (the explicit lookup checks `removed_players` which is
            # never updated). GW36 2026-05-09 hit this when player 47 got
            # paired with both 488 (fallback) and 237 (explicit pair),
            # producing FPL 400 "Element referenced more than once".
            used_outs: set = set()
            for player_in_id in new_players:
                player_out_id = None

                # 1. Honor explicit manager-recorded pair (normal transfers)
                if not skip_explicit_pairs:
                    for t in (draft_transfers or []):
                        t_in = t.get('player_in_id', t.get('element_in'))
                        t_out = t.get('player_out_id', t.get('element_out'))
                        if (t_in == player_in_id
                                and t_out in removed_players
                                and t_out not in used_outs):
                            player_out_id = t_out
                            et = player_type.get(t_out)
                            if et is not None and t_out in removed_by_type[et]:
                                removed_by_type[et].remove(t_out)
                            break

                # 2. Type-matched pairing (primary for WC/FH, fallback otherwise)
                if not player_out_id:
                    in_type = player_type.get(player_in_id)
                    # Defensive: drain any already-used players from the top
                    # of the same-type pool (shouldn't happen since we
                    # remove() on use, but guards against future regressions).
                    while (in_type is not None
                           and removed_by_type[in_type]
                           and removed_by_type[in_type][-1] in used_outs):
                        removed_by_type[in_type].pop()
                    if in_type is not None and removed_by_type[in_type]:
                        player_out_id = removed_by_type[in_type].pop()

                if player_out_id is not None:
                    used_outs.add(player_out_id)

                if not player_out_id:
                    logger.error(
                        f"Cannot pair player_in {player_in_id} "
                        f"(type {player_type.get(player_in_id)}) — no "
                        f"same-type player available in removed set"
                    )
                    continue

                player_in = db.execute_query(
                    "SELECT now_cost FROM players WHERE id = ?",
                    (player_in_id,)
                )

                purchase_price = player_in[0]['now_cost'] if player_in else 0
                # Prefer FPL's authoritative selling_price (from my_team).
                # Fall back to local DB only if somehow missing.
                selling_price = fpl_selling_price.get(player_out_id)
                if selling_price is None:
                    db_row = db.execute_query(
                        "SELECT selling_price FROM current_team WHERE player_id = ?",
                        (player_out_id,)
                    )
                    selling_price = db_row[0]['selling_price'] if db_row else 0

                transfers_for_api.append({
                    'element_in': player_in_id,
                    'element_out': player_out_id,
                    'purchase_price': purchase_price,
                    'selling_price': selling_price,
                })

            if transfers_for_api:
                transfer_chip = chip_used if chip_used in ('wildcard', 'freehit') else None
                transfer_result = self.submit_transfers(gameweek, transfers_for_api, chip=transfer_chip)
                results.append(transfer_result)

                if not transfer_result.success and not transfer_result.dry_run:
                    return SubmissionResult(
                        success=False, action='full', gameweek=gameweek,
                        message=f"Transfer submission failed: {transfer_result.message}",
                        details={'transfer_result': transfer_result.details}
                    )

                if not self.dry_run:
                    time.sleep(2)
        else:
            logger.info("No transfers needed (draft matches current FPL team)")

        # --- Step 3: Submit team selection ---
        # Fix bench ordering: FPL requires GK at position 12
        picks_for_api = []
        bench_players = [p for p in draft_team if p['position'] > 11]
        bench_gk = [p for p in bench_players if p['element_type'] == 1]
        bench_outfield = [p for p in bench_players if p['element_type'] != 1]

        for player in draft_team:
            if player['position'] <= 11:
                picks_for_api.append({
                    'element': player['player_id'],
                    'position': player['position'],
                    'is_captain': bool(player['is_captain']),
                    'is_vice_captain': bool(player['is_vice_captain']),
                })

        # Position 12 must be GK, 13-15 are outfield subs
        if bench_gk:
            picks_for_api.append({
                'element': bench_gk[0]['player_id'],
                'position': 12,
                'is_captain': False,
                'is_vice_captain': False,
            })
        for i, player in enumerate(bench_outfield):
            picks_for_api.append({
                'element': player['player_id'],
                'position': 13 + i,
                'is_captain': False,
                'is_vice_captain': False,
            })

        # Team endpoint handles bboost/3xc chips only. WC/FH are
        # "transfer chips" activated via the /transfers/ endpoint's
        # wildcard/freehit flags. Do NOT pass WC/FH here — the team
        # endpoint rejects with "wildcard is not a valid choice".
        team_chip = chip_used if chip_used in (
            'bboost', '3xc', 'bench_boost', 'triple_captain'
        ) else None
        team_result = self.submit_team(picks_for_api, chip=team_chip)
        team_result.gameweek = gameweek
        results.append(team_result)

        # --- Step 4: Summarize ---
        all_success = all(r.success for r in results)
        any_dry = any(r.dry_run for r in results)

        if all_success:
            # Update local DB to reflect the submission
            if not any_dry:
                db.confirm_draft_to_current(gameweek)
                logger.info(f"Draft confirmed as current team for GW{gameweek}")

            transfer_count = len(draft_transfers) if draft_transfers else 0
            captain = next((p for p in draft_team if p['is_captain']), None)
            captain_name = captain['web_name'] if captain else 'Unknown'

            message = (
                f"GW{gameweek} submitted: {transfer_count} transfer(s), "
                f"captain={captain_name}"
            )
            if chip_used:
                message += f", chip={chip_used}"
            if any_dry:
                message = f"DRY RUN: {message}"

            return SubmissionResult(
                success=True, action='full', gameweek=gameweek,
                message=message,
                details={
                    'transfers': transfer_count,
                    'captain': captain_name,
                    'chip': chip_used,
                },
                dry_run=any_dry,
            )
        else:
            failed = [r for r in results if not r.success]
            return SubmissionResult(
                success=False, action='full', gameweek=gameweek,
                message=f"Submission partially failed: {failed[0].message}",
                details={'results': [r.message for r in results]}
            )

    def _detect_chip_from_draft(self, db: Database, gameweek: int) -> Optional[str]:
        """Detect if a chip was used in the draft for this gameweek."""
        # Primary source: decisions table (where manager_agent_v2 logs chip
        # decisions as decision_type='chip_usage' with decision_data JSON).
        try:
            import json
            row = db.execute_query(
                """SELECT decision_data FROM decisions
                   WHERE gameweek = ? AND decision_type = 'chip_usage'
                   ORDER BY id DESC LIMIT 1""",
                (gameweek,)
            )
            if row:
                data = row[0].get('decision_data')
                if isinstance(data, str):
                    data = json.loads(data)
                chip = data.get('chip') if isinstance(data, dict) else None
                if chip and chip != 'none':
                    return chip
        except Exception:
            pass

        # Legacy fallback: team_selections (may not exist)
        try:
            chip_row = db.execute_query(
                """SELECT chip_used FROM team_selections
                   WHERE gameweek = ? AND chip_used IS NOT NULL
                   ORDER BY created_at DESC LIMIT 1""",
                (gameweek,)
            )
            if chip_row and chip_row[0].get('chip_used'):
                return chip_row[0]['chip_used']
        except Exception:
            pass

        # Legacy fallback: transfers.chip column
        try:
            wc_row = db.execute_query(
                """SELECT DISTINCT chip FROM transfers
                   WHERE gameweek = ? AND chip IS NOT NULL""",
                (gameweek,)
            )
            if wc_row and wc_row[0].get('chip'):
                return wc_row[0]['chip']
        except Exception:
            pass

        return None

    def verify_submission(self, gameweek: int) -> Dict[str, Any]:
        """
        Verify the submission by fetching the team back from FPL.

        Returns comparison of what we submitted vs what FPL shows.
        """
        db = Database()
        draft_team = db.get_draft_team(gameweek)
        my_team = self.get_my_team()

        if not my_team or not draft_team:
            return {'verified': False, 'reason': 'Could not fetch data for comparison'}

        fpl_picks = {p['element']: p for p in my_team.get('picks', [])}
        draft_players = {p['player_id']: p for p in draft_team}

        # Check all draft players are in FPL team
        missing = set(draft_players.keys()) - set(fpl_picks.keys())
        extra = set(fpl_picks.keys()) - set(draft_players.keys())

        # Check captain
        fpl_captain = next((p['element'] for p in my_team['picks'] if p['is_captain']), None)
        draft_captain = next((p['player_id'] for p in draft_team if p['is_captain']), None)

        verified = not missing and not extra and fpl_captain == draft_captain

        result = {
            'verified': verified,
            'missing_from_fpl': list(missing),
            'extra_in_fpl': list(extra),
            'captain_match': fpl_captain == draft_captain,
            'fpl_captain': fpl_captain,
            'draft_captain': draft_captain,
        }

        if verified:
            logger.info(f"GW{gameweek} submission VERIFIED - FPL matches draft")
        else:
            logger.warning(f"GW{gameweek} submission MISMATCH: {result}")

        return result


def submit_gameweek(gameweek: int, dry_run: bool = False) -> SubmissionResult:
    """
    Convenience function: login and submit a gameweek from draft.

    Args:
        gameweek: Target gameweek
        dry_run: If True, log actions without submitting

    Returns:
        SubmissionResult
    """
    client = FPLSubmissionClient(dry_run=dry_run)

    if not client.login():
        return SubmissionResult(
            success=False, action='full', gameweek=gameweek,
            message="FPL login failed"
        )

    return client.submit_gameweek_from_draft(gameweek)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Submit Ron\'s team to FPL')
    parser.add_argument('-g', '--gameweek', type=int, required=True,
                        help='Gameweek to submit')
    parser.add_argument('--dry-run', action='store_true',
                        help='Log actions without submitting')
    parser.add_argument('--verify', action='store_true',
                        help='Verify submission after submitting')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Verbose logging')
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
    )

    print(f"\n{'=' * 60}")
    print(f"FPL TEAM SUBMISSION - GAMEWEEK {args.gameweek}")
    if args.dry_run:
        print("MODE: DRY RUN (no changes will be made)")
    print(f"{'=' * 60}\n")

    result = submit_gameweek(args.gameweek, dry_run=args.dry_run)

    if result.success:
        print(f"\n{'=' * 60}")
        print(f"RESULT: {result.message}")
        print(f"{'=' * 60}")

        if args.verify and not args.dry_run:
            print("\nVerifying submission...")
            client = FPLSubmissionClient()
            client.login()
            verification = client.verify_submission(args.gameweek)
            if verification['verified']:
                print("VERIFIED: FPL team matches draft")
            else:
                print(f"MISMATCH: {verification}")
    else:
        print(f"\nFAILED: {result.message}")
        sys.exit(1)
