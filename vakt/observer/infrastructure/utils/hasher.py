from hashlib import sha256
from os import walk
from os.path import isfile, join


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
    Computes a SHA-256 checksum for the contents of a file system object
    at the specified path and returns a string with a hexadecimal
    representation (hex digest). Supports both files and directories,
    using a Merkle tree-based approach. This guarantees an identical,
    unchanging checksum for the same object state, regardless of the order
    in which the data is retrieved, which may vary across file systems.

    Designed for integrity checking and comparison of file system object
    contents, such as:
        - detecting implicit changes to object contents
        - verifying the integrity of backup data before use
        - comparing objects by content
        - detecting data corruption

    SHA-256 from the hashlib module is used because it provides a deterministic
    cryptographic digest with a very low probability of collisions.

    Notes:
        - The function assumes that the provided path exists and points
            to a readable file. So ensure that.!
        - If received object path is does not exist, the operation of this
            utility may break or return an incorrect result.
    """
    content_hash = sha256()

    if isfile(path):
        with open(path, "rb") as file:
            for chunk in iter(lambda: file.read(65536), b""):
                content_hash.update(chunk)

    else:
        for root, dirs, files in walk(path):
            dirs.sort()
            for file in sorted(files):
                file_path = join(root, file)
                content_hash.update(checksum(file_path).encode())

    return content_hash.hexdigest()
