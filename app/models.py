from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class Tile(BaseModel):
    """A single dashboard tile mapped to a Home Assistant entity."""

    id: str = Field(description="Unique tile identifier")
    entity_id: str = Field(description="Home Assistant entity ID, e.g. light.living_room")
    label: str = Field(description="Display label shown on the tile")
    icon: str = Field(default="mdi-toggle-switch", description="MDI icon name")
    domain: str = Field(description="HA domain: light, switch, fan, etc.")
    x: int = Field(default=0, ge=0, description="Grid column position")
    y: int = Field(default=0, ge=0, description="Grid row position")
    w: int = Field(default=2, ge=1, description="Width in grid units")
    h: int = Field(default=2, ge=1, description="Height in grid units")


class Layout(BaseModel):
    """Full dashboard layout — a list of tiles with grid column count."""

    columns: int = Field(default=12, ge=1, description="Grid column count")
    tiles: List[Tile] = Field(default_factory=list)


class ServiceCall(BaseModel):
    """Payload for calling a Home Assistant service."""

    entity_id: str
    extra: Optional[Dict] = Field(
        default=None,
        description="Optional additional service data (e.g. brightness, speed)",
    )
