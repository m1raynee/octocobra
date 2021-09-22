import io

import disnake

async def safe_send_prepare(content, **kwargs):
    """Same as send except with some safe guards.
    If the message is too long then it sends a file with the results instead.
    """

    if len(content) > 2000:
        fp = io.BytesIO(content.encode())
        kwargs.pop('file', None)
        return {
            'file': disnake.File(fp, filename='message_too_long.txt'),
            **kwargs
        }
    else:
        return {'content': content}