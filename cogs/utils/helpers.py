import io

import disnake

async def safe_send_prepare(content, *, escape_mentions=True, **kwargs):
    """Same as send except with some safe guards.
    1) If the message is too long then it sends a file with the results instead.
    2) If ``escape_mentions`` is ``True`` then it escapes mentions.
    """
    if escape_mentions:
        content = disnake.utils.escape_mentions(content)

    if len(content) > 2000:
        fp = io.BytesIO(content.encode())
        kwargs.pop('file', None)
        return {
            'file': disnake.File(fp, filename='message_too_long.txt'),
            **kwargs
        }
    else:
        return {'content': content}