import re

import disnake

__all__ = (
    'accept_mark',
    'deny_mark',
    'EMOJI_REGEX'
)

def _partial(name: str, id: int, animated: bool = False):
    return disnake.PartialEmoji(name=name, id=id, animated=animated)

EMOJI_REGEX = re.compile(r'(?P<animated>a?):(?P<name>[a-zA-Z0-9_]{2,32}):(?P<id>[0-9]{18,22})')
def _parse_string(string: str):
    match = re.match(EMOJI_REGEX, string)
    if match is None:
        raise TypeError(f'{string!r} is not valid emoji.')
    
    return _partial(*match.group('name', 'id', 'animated'))

accept_mark = _partial('accept_mark', 892770746013724683)
deny_mark = _partial('denny_mark', 892770746034704384)
choice_marks = (accept_mark, deny_mark)