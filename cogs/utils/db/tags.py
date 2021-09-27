from . import *

class TagTable(Model):
    id = IntField(pk=True)
    name = CharField(50, unique=True)

    content = TextField()
    owner_id = BigIntField()
    uses = IntField(default=0)
    created_at = DatetimeField(auto_now_add=True)

    aliases: ForeignKeyRelation['TagLookup']

    def __str__(self) -> str:
        return 'tag'

    class Meta:
        table = 'tags'

class TagLookup(Model):
    id = IntField(pk=True)
    name = CharField(50, unique=True)
    original: TagTable = ForeignKeyField('tags.TagTable', 'aliases')

    owner_id = BigIntField()
    created_at = DatetimeField(auto_now_add=True)

    def __str__(self) -> str:
        return 'tag alias'

    class Meta:
        table = 'tagslookup'
