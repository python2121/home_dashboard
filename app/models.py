from typing import Annotated, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, model_validator


class EntityTile(BaseModel):
    """A dashboard tile linked to a Home Assistant entity."""

    tile_type: Literal["entity"] = "entity"
    id: str = Field(description="Unique tile identifier")
    entity_id: str = Field(description="Home Assistant entity ID, e.g. light.living_room")
    label: str = Field(description="Display label shown on the tile")
    icon: str = Field(default="mdi-toggle-switch", description="MDI icon name")
    domain: str = Field(description="HA domain: light, switch, fan, etc.")
    badge_entity: Optional[str] = Field(
        default=None,
        description="Optional sensor entity ID whose state is shown as a small badge"
        " (e.g. sensor.filter_life)",
    )
    x: int = Field(default=0, ge=0, description="Grid column position")
    y: int = Field(default=0, ge=0, description="Grid row position")
    w: int = Field(default=2, ge=1, description="Width in grid units")
    h: int = Field(default=2, ge=1, description="Height in grid units")


class WeatherTile(BaseModel):
    """A dashboard tile showing current weather and forecast for a ZIP code."""

    tile_type: Literal["weather"] = "weather"
    id: str = Field(description="Unique tile identifier")
    label: str = Field(default="Weather", description="Display label shown on the tile")
    zip_code: str = Field(description="ZIP / postal code")
    country_code: str = Field(default="US", description="ISO 3166-1 alpha-2 country code")
    unit: Literal["fahrenheit", "celsius"] = Field(
        default="fahrenheit", description="Temperature unit"
    )
    x: int = Field(default=0, ge=0, description="Grid column position")
    y: int = Field(default=0, ge=0, description="Grid row position")
    w: int = Field(default=4, ge=1, description="Width in grid units")
    h: int = Field(default=4, ge=1, description="Height in grid units")


class SceneMember(BaseModel):
    """A single light in a scene with its own target brightness."""

    entity_id: str = Field(description="Home Assistant light entity ID")
    brightness: int = Field(default=255, ge=1, le=255, description="Target brightness (1–255)")


class SceneTile(BaseModel):
    """A dashboard tile that controls a group of lights, each at its own brightness."""

    tile_type: Literal["scene"] = "scene"
    id: str = Field(description="Unique tile identifier")
    label: str = Field(description="Display label shown on the tile")
    icon: str = Field(default="mdi-lightbulb-group", description="MDI icon name")
    members: List[SceneMember] = Field(
        description="Lights to control with individual brightness settings",
        min_length=1,
    )
    x: int = Field(default=0, ge=0, description="Grid column position")
    y: int = Field(default=0, ge=0, description="Grid row position")
    w: int = Field(default=2, ge=1, description="Width in grid units")
    h: int = Field(default=2, ge=1, description="Height in grid units")

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_members(cls, data):
        """Migrate old format: entity_ids + brightness → members list."""
        if isinstance(data, dict) and "entity_ids" in data and "members" not in data:
            brightness = data.get("brightness", 255)
            data["members"] = [
                {"entity_id": eid, "brightness": brightness}
                for eid in data.get("entity_ids", [])
            ]
        return data


class ClockTile(BaseModel):
    """A dashboard tile displaying the current time, date, and day of week."""

    tile_type: Literal["clock"] = "clock"
    id: str = Field(description="Unique tile identifier")
    label: str = Field(default="Clock", description="Display label shown on the tile")
    format_24h: bool = Field(default=False, description="Use 24-hour format")
    show_seconds: bool = Field(default=False, description="Display seconds")
    x: int = Field(default=0, ge=0, description="Grid column position")
    y: int = Field(default=0, ge=0, description="Grid row position")
    w: int = Field(default=2, ge=1, description="Width in grid units")
    h: int = Field(default=2, ge=1, description="Height in grid units")


class MoonTile(BaseModel):
    """A dashboard tile showing lunar phase, illumination, and rise/set times."""

    tile_type: Literal["moon"] = "moon"
    id: str = Field(description="Unique tile identifier")
    label: str = Field(default="Moon", description="Display label shown on the tile")
    zip_code: str = Field(description="ZIP / postal code for moonrise/set times")
    country_code: str = Field(default="US", description="ISO 3166-1 alpha-2 country code")
    x: int = Field(default=0, ge=0, description="Grid column position")
    y: int = Field(default=0, ge=0, description="Grid row position")
    w: int = Field(default=2, ge=1, description="Width in grid units")
    h: int = Field(default=2, ge=1, description="Height in grid units")


class ForecastChartTile(BaseModel):
    """A dashboard tile showing a rain or temperature chart for a ZIP code."""

    tile_type: Literal["forecast_chart"] = "forecast_chart"
    id: str = Field(description="Unique tile identifier")
    label: str = Field(default="Weather Chart", description="Display label shown on the tile")
    zip_code: str = Field(description="ZIP / postal code")
    country_code: str = Field(default="US", description="ISO 3166-1 alpha-2 country code")
    unit: Literal["fahrenheit", "celsius"] = Field(
        default="fahrenheit", description="Temperature unit"
    )
    x: int = Field(default=0, ge=0, description="Grid column position")
    y: int = Field(default=0, ge=0, description="Grid row position")
    w: int = Field(default=4, ge=1, description="Width in grid units")
    h: int = Field(default=3, ge=1, description="Height in grid units")


# Discriminated union — tile_type field selects the concrete model.
AnyTile = Annotated[
    Union[EntityTile, WeatherTile, SceneTile, ForecastChartTile, MoonTile, ClockTile],
    Field(discriminator="tile_type"),
]


class Layout(BaseModel):
    """Full dashboard layout — a list of tiles with grid column count."""

    columns: int = Field(default=12, ge=1, description="Grid column count")
    tiles: List[AnyTile] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _inject_tile_type(cls, data):
        """Backfill tile_type='entity' on tiles saved before the weather feature."""
        if isinstance(data, dict):
            for tile in data.get("tiles", []):
                if isinstance(tile, dict) and "tile_type" not in tile:
                    tile["tile_type"] = "entity"
        return data


class Room(BaseModel):
    """A named layout context (room)."""

    id: str = Field(description="Unique room identifier (URL-safe slug)")
    name: str = Field(description="Display name for the room")


class ServiceCall(BaseModel):
    """Payload for calling a Home Assistant service."""

    entity_id: str
    extra: Optional[Dict] = Field(
        default=None,
        description="Optional additional service data (e.g. brightness, speed)",
    )


class SceneToggle(BaseModel):
    """Request body for the scene-toggle endpoint."""

    members: List[SceneMember] = Field(
        description="Light members with individual brightness settings",
        min_length=1,
    )
    action: Literal["on", "off"] = Field(description="Whether to turn the group on or off")
