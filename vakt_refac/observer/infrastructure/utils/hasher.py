from hashlib import sha256


def hash_path(path: str) -> str:
    """
    Creates a deterministic SHA-256 hash for the original filesystem path and
    returns it as a hexadecimal digest string.

    Intended for cases where a path must be converted into a stable
    fixed-length identifier, for example:
            - storage data keys/names
            - indexing
            - deduplication
            - internal mapping keys
            - obscuring original filesystem paths

    SHA-256 from the hashlib module is used because it produces a
    consistent cryptographic digest with an extremely low probability
    of collisions.
    """
    return sha256(path.encode()).hexdigest()


def checksum(path: str) -> str:
    """
    Computes a SHA-256 checksum for the file content at the given path
    and returns it as a hexadecimal digest string.

    Intended for integrity verification and content comparison tasks,
    for example:
        - detecting file modifications
        - validating stored files
        - comparing files by content
        - identifying data corruption

    The file is read incrementally in chunks to avoid loading the
    entire file into memory, which keeps memory usage stable even
    for large files.

    SHA-256 from the hashlib module is used because it provides a deterministic
    cryptographic digest with a very low probability of collisions.

    Notes:
        - The function assumes that the provided path exists and points
            to a readable file. So ensure that!
    """
    content_hash = sha256()

    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(65536), b""):
            content_hash.update(chunk)

    return content_hash.hexdigest()
