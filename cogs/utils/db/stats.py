from . import *

class Commands(Model):
    id = BigIntField(pk=True)

    channel_id = BigIntField()
    author_id = BigIntField()
    used = DatetimeField(auto_now_add=True)
    command = CharField()
