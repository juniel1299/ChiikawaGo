"""In-memory execution summary; not a persisted job or revision record."""

from dataclasses import dataclass, field

from .parser import CollectionError


class TransientCollectionError(CollectionError):
    """A positively identified temporary transport failure, never an HTTP status."""


@dataclass(frozen=True)
class CollectionFailure:
    code: str
    stage: str
    retryable: bool = False


@dataclass
class CollectionResult:
    created: int = 0
    skipped: int = 0
    errors: list[CollectionFailure] = field(default_factory=list)

    @property
    def counts(self):
        return {"created": self.created, "skipped": self.skipped, "failed": len(self.errors)}

    @property
    def retryable(self):
        return bool(self.errors) and all(error.retryable for error in self.errors)

    def fail(self, exc, stage):
        self.errors.append(
            CollectionFailure(str(exc), stage, isinstance(exc, TransientCollectionError))
        )
