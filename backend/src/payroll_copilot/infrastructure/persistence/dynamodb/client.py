"""DynamoDB table client for the PayrollCopilot single-table design."""

from __future__ import annotations

import asyncio
import logging
from functools import lru_cache
from typing import Any

import boto3
from botocore.exceptions import ClientError

from payroll_copilot.infrastructure.config.settings import Settings, get_settings

logger = logging.getLogger(__name__)

GSI1 = "GSI1"
GSI2 = "GSI2"
GSI3 = "GSI3"


class DynamoTable:
    """Thin async wrapper around a boto3 DynamoDB Table resource."""

    def __init__(self, table_name: str, *, endpoint_url: str | None, region: str) -> None:
        self.table_name = table_name
        self._endpoint_url = endpoint_url
        self._region = region
        kwargs: dict[str, Any] = {"region_name": region}
        if endpoint_url:
            kwargs["endpoint_url"] = endpoint_url
            # DynamoDB Local accepts any credentials.
            kwargs.setdefault("aws_access_key_id", "local")
            kwargs.setdefault("aws_secret_access_key", "local")
        self._resource = boto3.resource("dynamodb", **kwargs)
        self._client = boto3.client("dynamodb", **kwargs)
        self._table = self._resource.Table(table_name)

    async def get_item(self, key: dict[str, Any]) -> dict[str, Any] | None:
        response = await asyncio.to_thread(self._table.get_item, Key=key)
        return response.get("Item")

    async def put_item(self, item: dict[str, Any]) -> None:
        await asyncio.to_thread(self._table.put_item, Item=item)

    async def update_item(
        self,
        key: dict[str, Any],
        *,
        update_expression: str,
        expression_attribute_values: dict[str, Any] | None = None,
        expression_attribute_names: dict[str, str] | None = None,
        condition_expression: Any = None,
        return_values: str = "ALL_NEW",
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "Key": key,
            "UpdateExpression": update_expression,
            "ReturnValues": return_values,
        }
        if expression_attribute_values:
            kwargs["ExpressionAttributeValues"] = expression_attribute_values
        if expression_attribute_names:
            kwargs["ExpressionAttributeNames"] = expression_attribute_names
        if condition_expression is not None:
            kwargs["ConditionExpression"] = condition_expression
        response = await asyncio.to_thread(self._table.update_item, **kwargs)
        return response.get("Attributes") or {}

    async def delete_item(self, key: dict[str, Any]) -> None:
        await asyncio.to_thread(self._table.delete_item, Key=key)

    async def query(
        self,
        *,
        key_condition_expression: Any,
        expression_attribute_values: dict[str, Any] | None = None,
        expression_attribute_names: dict[str, str] | None = None,
        index_name: str | None = None,
        scan_index_forward: bool = True,
        limit: int | None = None,
        filter_expression: Any = None,
    ) -> list[dict[str, Any]]:
        kwargs: dict[str, Any] = {
            "KeyConditionExpression": key_condition_expression,
            "ScanIndexForward": scan_index_forward,
        }
        if expression_attribute_values:
            kwargs["ExpressionAttributeValues"] = expression_attribute_values
        if expression_attribute_names:
            kwargs["ExpressionAttributeNames"] = expression_attribute_names
        if index_name:
            kwargs["IndexName"] = index_name
        if limit is not None:
            kwargs["Limit"] = limit
        if filter_expression is not None:
            kwargs["FilterExpression"] = filter_expression

        items: list[dict[str, Any]] = []
        exclusive_start_key = None
        while True:
            if exclusive_start_key:
                kwargs["ExclusiveStartKey"] = exclusive_start_key
            response = await asyncio.to_thread(self._table.query, **kwargs)
            items.extend(response.get("Items", []))
            exclusive_start_key = response.get("LastEvaluatedKey")
            if not exclusive_start_key:
                break
            if limit is not None and len(items) >= limit:
                break
        return items[:limit] if limit is not None else items

    async def query_eq_pk(
        self,
        pk: str,
        *,
        sk_begins_with: str | None = None,
        index_name: str | None = None,
        scan_index_forward: bool = True,
        limit: int | None = None,
        filter_expression: Any = None,
    ) -> list[dict[str, Any]]:
        from boto3.dynamodb.conditions import Key

        if index_name:
            key_cond = Key("GSI1PK" if index_name == GSI1 else (
                "GSI2PK" if index_name == GSI2 else "GSI3PK"
            )).eq(pk)
            sk_attr = (
                "GSI1SK" if index_name == GSI1 else ("GSI2SK" if index_name == GSI2 else "GSI3SK")
            )
            if sk_begins_with:
                key_cond = key_cond & Key(sk_attr).begins_with(sk_begins_with)
        else:
            key_cond = Key("PK").eq(pk)
            if sk_begins_with:
                key_cond = key_cond & Key("SK").begins_with(sk_begins_with)
        return await self.query(
            key_condition_expression=key_cond,
            index_name=index_name,
            scan_index_forward=scan_index_forward,
            limit=limit,
            filter_expression=filter_expression,
        )

    async def batch_delete(self, keys: list[dict[str, Any]]) -> int:
        if not keys:
            return 0
        deleted = 0
        # DynamoDB batch_writer handles chunking.
        def _run() -> int:
            count = 0
            with self._table.batch_writer() as batch:
                for key in keys:
                    batch.delete_item(Key=key)
                    count += 1
            return count

        deleted = await asyncio.to_thread(_run)
        return deleted

    async def describe(self) -> dict[str, Any]:
        return await asyncio.to_thread(self._client.describe_table, TableName=self.table_name)

    def ensure_table(self) -> None:
        """Create the single table + GSIs when missing (local/dev only)."""
        try:
            self._client.describe_table(TableName=self.table_name)
            return
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") != "ResourceNotFoundException":
                raise

        logger.info("Creating DynamoDB table %s (local/dev)", self.table_name)
        self._client.create_table(
            TableName=self.table_name,
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
                {"AttributeName": "GSI1PK", "AttributeType": "S"},
                {"AttributeName": "GSI1SK", "AttributeType": "S"},
                {"AttributeName": "GSI2PK", "AttributeType": "S"},
                {"AttributeName": "GSI2SK", "AttributeType": "S"},
                {"AttributeName": "GSI3PK", "AttributeType": "S"},
                {"AttributeName": "GSI3SK", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": GSI1,
                    "KeySchema": [
                        {"AttributeName": "GSI1PK", "KeyType": "HASH"},
                        {"AttributeName": "GSI1SK", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
                {
                    "IndexName": GSI2,
                    "KeySchema": [
                        {"AttributeName": "GSI2PK", "KeyType": "HASH"},
                        {"AttributeName": "GSI2SK", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
                {
                    "IndexName": GSI3,
                    "KeySchema": [
                        {"AttributeName": "GSI3PK", "KeyType": "HASH"},
                        {"AttributeName": "GSI3SK", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        waiter = self._client.get_waiter("table_exists")
        waiter.wait(TableName=self.table_name)


def create_dynamo_table(settings: Settings) -> DynamoTable:
    endpoint = (settings.dynamodb_endpoint or "").strip() or None
    if not endpoint and (settings.dynamodb_local_endpoint or "").strip():
        # Prefer explicit local endpoint only when DYNAMODB_ENDPOINT empty and local mode desired
        # via SERVICE auto — keep empty for Amazon DynamoDB by default.
        pass
    table = DynamoTable(
        settings.dynamodb_table_name.strip(),
        endpoint_url=endpoint,
        region=settings.dynamodb_region.strip() or settings.s3_region.strip() or "us-east-1",
    )
    if endpoint and settings.dynamodb_auto_create_table:
        table.ensure_table()
    return table


@lru_cache
def get_dynamo_table() -> DynamoTable:
    return create_dynamo_table(get_settings())
