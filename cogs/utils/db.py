from tortoise import Tortoise, run_async
from tortoise.models import Model
from tortoise.fields import *
from tortoise.expressions import *
from tortoise.transactions import in_transaction

from tortoise.backends.sqlite.client import TransactionWrapper

async def init():
    await Tortoise.init(config_file='tortoise.yaml')
    await Tortoise.generate_schemas()
