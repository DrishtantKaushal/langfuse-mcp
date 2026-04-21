"""Annotation queue tools — queue CRUD, queue items, and reviewer assignments."""
from __future__ import annotations
from typing import Any

_GROUP_MAP = {
    "annotation_queues": [
        "list_annotation_queues",
        "create_annotation_queue",
        "get_annotation_queue",
        "list_annotation_queue_items",
        "get_annotation_queue_item",
        "create_annotation_queue_item",
        "update_annotation_queue_item",
        "delete_annotation_queue_item",
        "create_annotation_queue_assignment",
        "delete_annotation_queue_assignment",
    ],
}


def register_annotation_queue_tools(mcp, client, enabled_groups: set[str] | None = None):
    """Register annotation queue tools.

    Gated behind the 'annotation_queues' group. If enabled_groups is set and does not
    include 'annotation_queues', nothing registers.
    """
    if enabled_groups is not None and "annotation_queues" not in enabled_groups:
        return

    @mcp.tool()
    async def list_annotation_queues(limit: int = 50, page: int = 1) -> dict:
        """List all annotation queues in the project."""
        return await client.get_annotation_queues(limit=limit, page=page)

    @mcp.tool()
    async def create_annotation_queue(
        name: str,
        score_config_ids: str,
        description: str | None = None,
    ) -> dict:
        """Create a new annotation queue.

        score_config_ids: comma-separated score config IDs to attach to the queue.
        """
        data: dict[str, Any] = {
            "name": name,
            "scoreConfigIds": [s.strip() for s in score_config_ids.split(",") if s.strip()],
        }
        if description:
            data["description"] = description
        return await client.create_annotation_queue(data)

    @mcp.tool()
    async def get_annotation_queue(queue_id: str) -> dict:
        """Get a single annotation queue by ID."""
        return await client.get_annotation_queue(queue_id)

    @mcp.tool()
    async def list_annotation_queue_items(
        queue_id: str,
        limit: int = 50,
        page: int = 1,
        status: str | None = None,
    ) -> dict:
        """List items in an annotation queue. status: PENDING or COMPLETED."""
        params: dict[str, Any] = {"limit": limit, "page": page}
        if status:
            params["status"] = status
        return await client.get_annotation_queue_items(queue_id, **params)

    @mcp.tool()
    async def get_annotation_queue_item(queue_id: str, item_id: str) -> dict:
        """Get a single queue item by ID."""
        return await client.get_annotation_queue_item(queue_id, item_id)

    @mcp.tool()
    async def create_annotation_queue_item(
        queue_id: str,
        object_id: str,
        object_type: str,
        status: str | None = None,
    ) -> dict:
        """Add a trace or observation to an annotation queue for review.

        object_type: 'TRACE' or 'OBSERVATION'.
        status: optional initial status (defaults to PENDING).
        """
        data: dict[str, Any] = {"objectId": object_id, "objectType": object_type}
        if status:
            data["status"] = status
        return await client.create_annotation_queue_item(queue_id, data)

    @mcp.tool()
    async def update_annotation_queue_item(
        queue_id: str,
        item_id: str,
        status: str,
    ) -> dict:
        """Update a queue item's status. status: PENDING or COMPLETED."""
        return await client.update_annotation_queue_item(
            queue_id, item_id, {"status": status}
        )

    @mcp.tool()
    async def delete_annotation_queue_item(queue_id: str, item_id: str) -> dict:
        """Remove an item from an annotation queue."""
        return await client.delete_annotation_queue_item(queue_id, item_id)

    @mcp.tool()
    async def create_annotation_queue_assignment(queue_id: str, user_id: str) -> dict:
        """Assign a reviewer (user) to an annotation queue."""
        return await client.create_annotation_queue_assignment(queue_id, user_id)

    @mcp.tool()
    async def delete_annotation_queue_assignment(queue_id: str, user_id: str) -> dict:
        """Remove a reviewer assignment from an annotation queue."""
        return await client.delete_annotation_queue_assignment(queue_id, user_id)
