import io

import disnake

from .views import Delete

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

async def wait_for_deletion(
    author_id: int,
    message_kwargs: dict,
    destination: disnake.abc.Messageable,
    timeout: float = 60 * 5
) -> None:
    view = Delete(listen_to=[author_id], timeout=timeout)
    message_kwargs['view'] = view
    await destination.send(**message_kwargs)