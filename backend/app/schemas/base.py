from pydantic import BaseModel, ConfigDict


class Contract(BaseModel):
    """Base for every contract model: unknown fields are rejected, never ignored."""

    model_config = ConfigDict(extra="forbid", use_enum_values=False)
