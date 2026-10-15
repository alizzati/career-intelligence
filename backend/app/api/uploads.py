"""Bounded upload reading."""
from app.api.errors import ApiError


async def read_upload_bounded(upload, max_bytes: int, chunk_bytes: int) -> bytes:
    """Read in chunks and stop as soon as the limit is exceeded."""
    buffer = bytearray()
    while True:
        chunk = await upload.read(chunk_bytes)
        if not chunk:
            break
        buffer.extend(chunk)
        if len(buffer) > max_bytes:
            raise ApiError(413, "file_too_large",
                           f"Document exceeds the {max_bytes}-byte file-size limit.")
    return bytes(buffer)  # the extractor requires bytes, not bytearray