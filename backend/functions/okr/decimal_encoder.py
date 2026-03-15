"""
Shared utility: JSON encoder that converts DynamoDB Decimal types to float/int.
boto3 deserialises all DynamoDB Number types as decimal.Decimal.
json.dumps default=str would turn Decimal('4.2') into the string "4.2" which
breaks numeric comparisons in the frontend. This encoder converts to float instead.
"""
import json
from decimal import Decimal


class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            # Return int if the value is whole, float otherwise
            return int(obj) if obj % 1 == 0 else float(obj)
        return super().default(obj)


def dumps(obj) -> str:
    return json.dumps(obj, cls=DecimalEncoder)
