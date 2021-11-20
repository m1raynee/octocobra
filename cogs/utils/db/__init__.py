from tortoise import Tortoise, run_async
from tortoise.expressions import *
from tortoise.transactions import in_transaction

from tortoise.backends.sqlite.client import TransactionWrapper

TORTOISE_ORM = {
    'apps': {
        'app': {
            'models': [
                'cogs.utils.db.tags',
                'cogs.utils.db.remind',
                'cogs.utils.db.users',
                'aerich.models'
            ],
            'default_connection': 'master'
        }
    },
    'connections': {'master': 'sqlite://data/db.sqlite'}
}

async def init(*, reload=True):
    if reload:
        await Tortoise.close_connections()
    await Tortoise.init(config=TORTOISE_ORM)
    if reload:
        await Tortoise.generate_schemas()
