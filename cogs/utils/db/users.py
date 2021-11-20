from tortoise.models import Model
from tortoise.fields import (
    BigIntField, 
    IntField
)

class User(Model):
    discord_id = BigIntField(True)
    karma = IntField()
    helper_at = IntField()
