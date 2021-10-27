from tortoise import Tortoise, run_async
from tortoise.models import Model
from tortoise.fields import *
from tortoise.expressions import *
from tortoise.transactions import in_transaction

from tortoise.backends.sqlite.client import TransactionWrapper

TORTOISE_ORM = {
    'apps': {
        'tags': {
            'models': ['cogs.utils.db.tags', 'aerich.models'],
            'default_connection': 'master'
        },
        'remind': {
            'models': ['cogs.utils.db.remind', 'aerich.models'],
            'default_connection': 'master'
        }
    },
    'connections': {'master': 'sqlite://data/db.sqlite'}
}

async def init(*, close_connections=True):
    if close_connections:
        await Tortoise.close_connections()
    await Tortoise.init(config=TORTOISE_ORM)
