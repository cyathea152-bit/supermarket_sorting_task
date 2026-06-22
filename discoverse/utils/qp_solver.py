def select_qp_solver(preferred="quadprog", fallback="daqp"):
    """Return an installed qpsolvers backend, preferring the requested solver."""
    try:
        from qpsolvers import available_solvers
    except Exception:
        return preferred

    if preferred in available_solvers:
        return preferred
    if fallback in available_solvers:
        return fallback
    return preferred
