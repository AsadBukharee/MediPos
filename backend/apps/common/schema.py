"""Small helper for documenting plain APIViews in the OpenAPI schema."""
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema


def documented(summary: str, *, params: tuple[str, ...] = (), body: bool = False, empty: bool = False):
    """Describe an endpoint whose request/response is a free-form JSON object."""
    return extend_schema(
        summary=summary,
        parameters=[OpenApiParameter(name, OpenApiTypes.STR, OpenApiParameter.QUERY) for name in params],
        request=OpenApiTypes.OBJECT if body else None,
        responses={204: None} if empty else OpenApiTypes.OBJECT,
    )
