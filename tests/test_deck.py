"""Tests for server.deck."""

from __future__ import annotations

import random

import pytest

from server.deck import generate_tarot_sequence

EXPECTED_MAJOR = {f"{i:02d}" for i in range(1, 23)}
EXPECTED_MINOR = {
    f"{prefix}{rank:02d}"
    for prefix in ("c", "p", "s", "w")
    for rank in range(1, 15)
}
EXPECTED_ALL_IDS = EXPECTED_MAJOR | EXPECTED_MINOR


@pytest.fixture
def deterministic_deck(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shuffle and orientation become predictable."""

    def stable_shuffle(deck: list[str]) -> None:
        deck.sort()

    monkeypatch.setattr(random, "shuffle", stable_shuffle)
    monkeypatch.setattr(random, "choice", lambda _seq: False)


def test_generate_tarot_sequence_has_78_positions() -> None:
    """Sequence keys are positions 1 through 78."""
    sequence = generate_tarot_sequence()
    assert len(sequence) == 78
    assert set(sequence.keys()) == {str(i) for i in range(1, 79)}


def test_generate_tarot_sequence_contains_full_deck(
    deterministic_deck: None,
) -> None:
    """Every standard card id appears exactly once."""
    sequence = generate_tarot_sequence()
    ids = {entry["id"] for entry in sequence.values()}
    assert ids == EXPECTED_ALL_IDS


def test_generate_tarot_sequence_entry_shape(
    deterministic_deck: None,
) -> None:
    """Each slot has id (str) and reversed (bool)."""
    sequence = generate_tarot_sequence()
    first = sequence["1"]
    
    # Check the structure, not specific values
    assert "id" in first
    assert "reversed" in first
    assert isinstance(first["id"], str)
    assert isinstance(first["reversed"], bool)
    
    # Check that id has correct format (2-3 chars: "01" or "w10" etc.)
    assert len(first["id"]) in (2, 3)
    
    # Check orientation is boolean
    assert first["reversed"] in (True, False)


def test_generate_tarot_sequence_reversed_can_be_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reversed flag follows random.choice."""
    monkeypatch.setattr(random, "shuffle", lambda deck: deck.sort())
    monkeypatch.setattr(random, "choice", lambda _seq: True)
    sequence = generate_tarot_sequence()
    assert all(entry["reversed"] is True for entry in sequence.values())


def test_generate_tarot_sequence_reversed_can_be_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reversed flag can be False."""
    monkeypatch.setattr(random, "shuffle", lambda deck: deck.sort())
    monkeypatch.setattr(random, "choice", lambda _seq: False)
    sequence = generate_tarot_sequence()
    assert all(entry["reversed"] is False for entry in sequence.values())

def test_generate_tarot_sequence_shuffles_deck() -> None:
    """Multiple calls produce different orders (probabilistically)."""
    # Run multiple times - extremely unlikely to get same order twice
    sequence1 = generate_tarot_sequence()
    sequence2 = generate_tarot_sequence()
    sequence3 = generate_tarot_sequence()
    
    orders = [
        [entry["id"] for entry in seq.values()] 
        for seq in (sequence1, sequence2, sequence3)
    ]
    
    # With 78! possibilities, probability of collision is astronomical
    assert len(set(tuple(order) for order in orders)) > 1

def test_generate_tarot_sequence_no_duplicate_positions() -> None:
    """Each position 1-78 appears exactly once."""
    sequence = generate_tarot_sequence()
    positions = list(sequence.keys())
    
    assert len(positions) == len(set(positions))
    assert sorted(map(int, positions)) == list(range(1, 79))

def test_generate_tarot_sequence_reversed_distribution() -> None:
    """Reversed flag approximates 50/50 distribution (probabilistic)."""
    import statistics
    
    # Run multiple decks to smooth randomness
    reversed_counts = []
    for _ in range(100):
        sequence = generate_tarot_sequence()
        reversed_count = sum(1 for entry in sequence.values() if entry["reversed"])
        reversed_counts.append(reversed_count)
    
    mean_reversed = statistics.mean(reversed_counts)
    # With 78 cards, expect ~39 reversed, allow +/- 15 margin for 100 samples
    assert 30 < mean_reversed < 48

def test_deterministic_deck_consistency(deterministic_deck: None) -> None:
    """The deterministic fixture always produces the same order."""
    seq1 = generate_tarot_sequence()
    seq2 = generate_tarot_sequence()
    seq3 = generate_tarot_sequence()
    
    # All should be identical
    assert seq1 == seq2 == seq3
    
    # With deterministic_deck, cards should be in sorted order
    ids = [entry["id"] for entry in seq1.values()]
    assert ids == sorted(EXPECTED_ALL_IDS)
    
    # All should be upright (False)
    assert all(entry["reversed"] is False for entry in seq1.values())

@pytest.mark.parametrize("card_id", [
    "01", "22",  # Major arcana boundaries
    "c01", "c14",  # Minor arcana: cups
    "p01", "p14",  # Pentacles
    "s01", "s14",  # Swords
    "w01", "w14",  # Wands
])
def test_generate_tarot_sequence_valid_card_formats(card_id: str) -> None:
    """All generated card IDs follow expected formats."""
    # Force deck to contain our test IDs by mocking?
    # Alternatively, just verify the function only produces valid formats
    for _ in range(20):  # Multiple runs
        sequence = generate_tarot_sequence()
        for entry in sequence.values():
            card_id = entry["id"]
            # Major: 2 digits 01-22
            # Minor: letter + 2 digits 01-14
            assert (len(card_id) == 2 and card_id.isdigit() and 1 <= int(card_id) <= 22) or \
                   (len(card_id) == 3 and card_id[0] in "cpsw" and card_id[1:].isdigit() and 1 <= int(card_id[1:]) <= 14)

def test_generate_tarot_sequence_does_not_share_state() -> None:
    """Multiple calls return independent sequences (no shared slot objects)."""
    seq1 = generate_tarot_sequence()
    seq2 = generate_tarot_sequence()

    seq2_reversed_before = seq2["1"]["reversed"]
    seq1["1"]["reversed"] = not seq1["1"]["reversed"]

    assert seq1["1"] is not seq2["1"]
    assert seq2["1"]["reversed"] == seq2_reversed_before

def test_generate_tarot_sequence_first_last_positions() -> None:
    """First and last positions exist and have correct structure."""
    sequence = generate_tarot_sequence()
    
    assert "1" in sequence
    assert "78" in sequence
    
    first = sequence["1"]
    last = sequence["78"]
    
    assert "id" in first and "reversed" in first
    assert "id" in last and "reversed" in last