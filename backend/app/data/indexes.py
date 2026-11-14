"""Atlas Vector Search definitions. Provision explicitly, never at match startup."""

STYLE_INDEX = "style_profiles_vector"
EXPERIENCE_INDEX = "coach_experiences_vector"


def vector_index_definition(dimensions: int, *, experiences: bool = False) -> dict:
    if isinstance(dimensions, bool) or not isinstance(dimensions, int) or dimensions < 1:
        raise ValueError("dimensions must be a positive integer")
    filters = ["namespace", "embedding_model"]
    if experiences:
        filters += ["verified", "occurred_at"]
    return {
        "fields": [
            {
                "type": "vector",
                "path": "embedding",
                "numDimensions": dimensions,
                "similarity": "cosine",
            },
            *[{"type": "filter", "path": field} for field in filters],
        ]
    }
