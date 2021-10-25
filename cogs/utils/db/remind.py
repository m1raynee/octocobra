from . import *

class Reminders(Model):
    id = BigIntField(pk=True)

    expires = DatetimeField()
    created = DatetimeField(auto_now_add=True)
    event = CharField(32)
    extra = JSONField(default={})
    author_id = BigIntField()

    class Meta:
        table = 'remind'