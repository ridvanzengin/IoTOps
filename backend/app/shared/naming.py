import re

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def slugify(value: str, *, max_length: int = 40, fallback: str = "unnamed") -> str:
    """Lowercase, hyphen-joined slug of `value`, safe for a Docker
    container name/hostname. Falls back to `fallback` if the input has no
    ASCII alphanumeric characters at all (e.g. a name written entirely in
    an unsupported script or emoji) -- container names must be non-empty.
    """
    slug = _NON_ALNUM_RE.sub("-", value.strip().lower()).strip("-")
    return slug[:max_length].strip("-") or fallback
