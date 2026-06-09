"""Unit tests for the entry state machine (budget, sell prices, FTs, chips)."""

import pytest

from backtest.scoring import BENCH_BOOST, FREE_HIT, TRIPLE_CAPTAIN, WILDCARD
from backtest.state import (
    EntryState,
    IllegalSquadError,
    IllegalTransferError,
    OwnedPlayer,
    Transfer,
    sell_price,
    validate_squad,
)


class TestSellPrice:
    def test_no_profit_sells_at_current(self):
        assert sell_price(50, 50) == 50

    def test_price_fall_sells_at_current(self):
        assert sell_price(50, 47) == 47

    def test_profit_halved_rounded_down(self):
        assert sell_price(50, 51) == 50   # +0.1 -> no bonus
        assert sell_price(50, 52) == 51   # +0.2 -> +0.1
        assert sell_price(50, 53) == 51   # +0.3 -> +0.1
        assert sell_price(50, 60) == 55   # +1.0 -> +0.5


class TestSquadValidation:
    def _legal(self):
        # 2 GK, 5 DEF, 5 MID, 3 FWD across enough clubs
        types, teams = {}, {}
        pid = 1
        for et, n in [(1, 2), (2, 5), (3, 5), (4, 3)]:
            for _ in range(n):
                types[pid] = et
                teams[pid] = pid % 10
                pid += 1
        return set(types), types, teams

    def test_legal_squad_passes(self):
        ids, types, teams = self._legal()
        validate_squad(ids, types, teams)

    def test_wrong_shape_fails(self):
        ids, types, teams = self._legal()
        types[1] = 2  # 1 GK, 6 DEF
        with pytest.raises(IllegalSquadError):
            validate_squad(ids, types, teams)

    def test_four_from_one_club_fails(self):
        ids, types, teams = self._legal()
        for pid in [3, 4, 5, 6]:
            teams[pid] = 99
        with pytest.raises(IllegalSquadError):
            validate_squad(ids, types, teams)


class TestFreeTransfers:
    def test_accrual_caps_at_five(self):
        s = EntryState()
        assert s.available_ft(8) == 1
        for gw in range(8, 14):
            s.apply_gameweek(gw, [], chip=None, prices={})
        assert s.available_ft(14) == 5

    def test_hits_charged_beyond_available(self):
        s = EntryState(banked_ft=1)  # 2 available
        s.squad = {pid: OwnedPlayer(pid, 50) for pid in range(1, 16)}
        transfers = [
            Transfer(out_id=pid, in_id=pid + 100, out_price=50, in_price=50)
            for pid in range(1, 5)
        ]
        hit = s.apply_gameweek(10, transfers, chip=None, prices={})
        assert hit == 8  # 4 transfers, 2 free
        assert s.banked_ft == 0

    def test_wildcard_freezes_ft_no_accrual_no_hits(self):
        s = EntryState(banked_ft=1)
        s.squad = {pid: OwnedPlayer(pid, 50) for pid in range(1, 16)}
        transfers = [
            Transfer(out_id=pid, in_id=pid + 100, out_price=50, in_price=50)
            for pid in range(1, 11)
        ]
        hit = s.apply_gameweek(19, transfers, chip=WILDCARD, prices={})
        assert hit == 0
        assert s.banked_ft == 1            # frozen, not reset, no +1
        assert s.available_ft(20) == 2

    def test_afcon_topup(self):
        s = EntryState(banked_ft=0, ft_topups={16: 5})
        assert s.available_ft(15) == 1
        assert s.available_ft(16) == 5

    def test_rons_gw36_hit_reproduced(self):
        """Walk Ron's actual 2025-26 transfer counts through the machine:
        the GW36 cost must come out at 28 (9 transfers, 2 FTs)."""
        usage = {12: 2, 14: 4, 15: 1, 16: 1, 17: 1, 20: 3, 21: 2, 23: 2,
                 24: 2, 26: 2, 27: 1, 28: 1, 30: 1, 31: 1, 32: 1, 33: 1,
                 36: 9}
        chips = {13: TRIPLE_CAPTAIN, 17: BENCH_BOOST, 18: FREE_HIT,
                 19: WILDCARD, 34: WILDCARD, 35: FREE_HIT,
                 36: TRIPLE_CAPTAIN, 38: BENCH_BOOST}
        s = EntryState(ft_topups={16: 5})
        s.squad = {pid: OwnedPlayer(pid, 50) for pid in range(1, 16)}
        pool = iter(range(1000, 2000))
        hits = {}
        for gw in range(8, 39):
            chip = chips.get(gw)
            n = 0 if chip in (WILDCARD, FREE_HIT) else usage.get(gw, 0)
            outs = list(s.squad)[:n]
            transfers = [
                Transfer(out_id=out, in_id=next(pool), out_price=50, in_price=50)
                for out in outs
            ]
            hits[gw] = s.apply_gameweek(gw, transfers, chip=chip, prices={})
        assert hits[36] == 28
        assert all(h == 0 for gw, h in hits.items() if gw != 36)


class TestChips:
    def test_two_of_each_chip_by_half(self):
        s = EntryState()
        s.squad = {pid: OwnedPlayer(pid, 50) for pid in range(1, 16)}
        assert s.chip_available(WILDCARD, 10)
        s.apply_gameweek(10, [], chip=WILDCARD, prices={})
        assert not s.chip_available(WILDCARD, 15)   # first half used
        assert s.chip_available(WILDCARD, 25)       # second half fresh
        s.apply_gameweek(25, [], chip=WILDCARD, prices={})
        assert not s.chip_available(WILDCARD, 30)

    def test_unavailable_chip_rejected(self):
        s = EntryState()
        s.squad = {pid: OwnedPlayer(pid, 50) for pid in range(1, 16)}
        s.apply_gameweek(10, [], chip=FREE_HIT, prices={})
        with pytest.raises(IllegalTransferError):
            s.apply_gameweek(12, [], chip=FREE_HIT, prices={})


class TestTransferEconomics:
    def test_bank_updates_with_recorded_prices(self):
        s = EntryState(bank=10)
        s.squad = {1: OwnedPlayer(1, 50)} | {
            pid: OwnedPlayer(pid, 50) for pid in range(2, 16)
        }
        s.apply_gameweek(10, [Transfer(1, 99, out_price=64, in_price=51)],
                         chip=None, prices={})
        assert s.bank == 10 + 64 - 51
        assert 99 in s.squad and s.squad[99].purchase_price == 51

    def test_sell_price_used_when_no_recorded_price(self):
        s = EntryState(bank=0)
        s.squad = {pid: OwnedPlayer(pid, 50) for pid in range(1, 16)}
        # Player 1 bought at 50, now worth 54 -> sells for 52
        s.apply_gameweek(10, [Transfer(1, 99)], chip=None,
                         prices={1: 54, 99: 52})
        assert s.bank == 0

    def test_negative_bank_rejected(self):
        s = EntryState(bank=0)
        s.squad = {pid: OwnedPlayer(pid, 50) for pid in range(1, 16)}
        with pytest.raises(IllegalTransferError):
            s.apply_gameweek(10, [Transfer(1, 99)], chip=None,
                             prices={1: 50, 99: 60})

    def test_cannot_sell_unowned_or_buy_owned(self):
        s = EntryState()
        s.squad = {pid: OwnedPlayer(pid, 50) for pid in range(1, 16)}
        with pytest.raises(IllegalTransferError):
            s.apply_gameweek(10, [Transfer(99, 100)], chip=None, prices={})
        with pytest.raises(IllegalTransferError):
            s.apply_gameweek(10, [Transfer(1, 2)], chip=None, prices={})

    def test_within_window_churn_resolves_sequentially(self):
        """Wildcard pattern: buy a player then sell him again same window."""
        s = EntryState(bank=0)
        s.squad = {pid: OwnedPlayer(pid, 50) for pid in range(1, 16)}
        transfers = [
            Transfer(1, 99, out_price=50, in_price=45),   # bank +5
            Transfer(99, 1, out_price=45, in_price=50),   # bank back to 0
        ]
        s.apply_gameweek(10, transfers, chip=WILDCARD, prices={})
        assert s.bank == 0
        assert 1 in s.squad and 99 not in s.squad


class TestFreeHitSnapshot:
    def test_snapshot_restore_round_trip(self):
        s = EntryState(bank=7)
        s.squad = {pid: OwnedPlayer(pid, 50) for pid in range(1, 16)}
        snap = s.snapshot()
        s.apply_gameweek(18, [Transfer(1, 99, out_price=50, in_price=40)],
                         chip=FREE_HIT, prices={})
        assert 99 in s.squad and s.bank == 17
        s.restore(snap)
        assert 1 in s.squad and 99 not in s.squad
        assert s.bank == 7
