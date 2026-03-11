"""Tests for the ClockTile model.

Clock is a pure frontend tile — no backend route. These tests verify the
Pydantic model defaults, serialization round-trip, and discriminator.
"""

from app.models import ClockTile, Layout


def test_clock_tile_defaults():
    tile = ClockTile(id="clk_1")
    assert tile.tile_type == "clock"
    assert tile.label == "Clock"
    assert tile.format_24h is False
    assert tile.show_seconds is False
    assert tile.w == 2
    assert tile.h == 2


def test_clock_tile_custom_values():
    tile = ClockTile(
        id="clk_2",
        label="Kitchen Clock",
        format_24h=True,
        show_seconds=True,
        x=4,
        y=2,
        w=3,
        h=3,
    )
    assert tile.label == "Kitchen Clock"
    assert tile.format_24h is True
    assert tile.show_seconds is True
    assert tile.x == 4
    assert tile.w == 3


def test_clock_tile_in_layout_roundtrip():
    layout_data = {
        "columns": 12,
        "tiles": [
            {
                "tile_type": "clock",
                "id": "clk_rt",
                "label": "Office",
                "format_24h": True,
                "show_seconds": False,
                "x": 0,
                "y": 0,
                "w": 2,
                "h": 2,
            }
        ],
    }
    layout = Layout(**layout_data)
    assert len(layout.tiles) == 1
    tile = layout.tiles[0]
    assert tile.tile_type == "clock"
    assert tile.label == "Office"
    assert tile.format_24h is True
    assert tile.show_seconds is False

    # Round-trip through dict
    dumped = layout.model_dump()
    restored = Layout(**dumped)
    assert restored.tiles[0].tile_type == "clock"
    assert restored.tiles[0].id == "clk_rt"


def test_clock_tile_discriminator():
    """Verify tile_type='clock' correctly round-trips through the AnyTile union."""
    layout = Layout(
        tiles=[
            {
                "tile_type": "clock",
                "id": "clk_disc",
                "x": 0,
                "y": 0,
                "w": 2,
                "h": 2,
            }
        ]
    )
    tile = layout.tiles[0]
    assert type(tile).__name__ == "ClockTile"
    assert tile.tile_type == "clock"
