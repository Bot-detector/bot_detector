from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class WorkerError(Exception, Generic[T]):
    """Returned by a Worker from handle() to signal a batch failure.

    Carries the items that were processed successfully (ok_batch) and the
    items that failed (error_batch). The WorkerRunner re-publishes
    error_batch and commits the original batch offsets; ok_batch is
    considered done and is not requeued.

    This is the errors-as-values equivalent of raising, preferred inside
    components per the "handle errors as values" guideline. Use it when you
    need to record which items succeeded despite the failure, or to keep
    component code free of raises. Workers must be idempotent on re-delivery
    of error_batch items.

    Example:
        return WorkerError(
            "insert failed for N rows",
            ok_batch=processed,
            error_batch=failed,
        )
    """

    def __init__(
        self,
        message: str,
        *,
        ok_batch: list[T],
        error_batch: list[T],
    ) -> None:
        super().__init__(message)
        self.ok_batch = ok_batch
        self.error_batch = error_batch
