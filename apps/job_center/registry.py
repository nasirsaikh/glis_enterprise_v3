from typing import Callable

JOB_REGISTRY: dict[str, Callable] = {}


def register_job(name: str):
    def decorator(func: Callable):
        if name in JOB_REGISTRY:
            raise ValueError(f"Job handler '{name}' is already registered.")
        JOB_REGISTRY[name] = func
        return func
    return decorator


def get_job_handler(name: str) -> Callable:
    handler = JOB_REGISTRY.get(name)
    if handler is None:
        available = ", ".join(sorted(JOB_REGISTRY)) or "(none registered)"
        raise ValueError(
            f"Unknown job handler '{name}'. Registered handlers: {available}"
        )
    return handler


def get_registered_jobs():
    return JOB_REGISTRY.copy()
