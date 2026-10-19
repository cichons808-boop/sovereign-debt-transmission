"""Weighted LASSO by cyclic coordinate descent, using array operations only.

The caller supplies columns divided by their penalty loadings. The objective is
||y - X b||^2/(2 n) + alpha * sum(abs(b)). No intercept is fitted here: mandatory
controls have already been projected out. Convergence is checked against both
the primal-dual gap and the coordinatewise optimality conditions.
"""
import numpy as np


def soft_threshold(value, threshold):
    return np.sign(value) * max(abs(value) - threshold, 0.)


def coordinate_descent(x, y, alpha, max_iter=20000, tol=1e-11):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    n, p = x.shape
    if len(y) != n or alpha <= 0:
        raise ValueError('Invalid LASSO dimensions or penalty')
    gram = x.T @ x / n
    xy = x.T @ y / n
    yy = float(y @ y / n)
    diagonal = np.diag(gram)
    if np.any(diagonal <= 0):
        raise ValueError('LASSO requires nonzero columns')
    beta = np.zeros(p)
    gradient = xy.copy()
    converged = False
    gap = kkt = np.inf
    for iteration in range(1, max_iter + 1):
        largest_change = 0.
        for j in range(p):
            updated = soft_threshold(gradient[j] + diagonal[j] * beta[j], alpha) / diagonal[j]
            change = updated - beta[j]
            if change:
                beta[j] = updated
                gradient -= gram[:, j] * change
                largest_change = max(largest_change, abs(change))
        # Recompute from the normal equations to avoid accumulated roundoff.
        gradient = xy - gram @ beta
        active = beta != 0
        violations = np.maximum(abs(gradient) - alpha, 0.)
        violations[active] = abs(gradient[active] - alpha * np.sign(beta[active]))
        kkt = float(np.max(violations, initial=0.))
        if largest_change <= 1e-7 * max(1., float(np.max(abs(beta), initial=0.))) or iteration % 50 == 0:
            residual = y - x @ beta
            multiplier = min(1., alpha / max(float(np.max(abs(x.T @ residual / n), initial=0.)), 1e-300))
            dual_residual = multiplier * residual
            primal = float(residual @ residual / (2 * n) + alpha * abs(beta).sum())
            dual = float((2 * y @ dual_residual - dual_residual @ dual_residual) / (2 * n))
            gap = max(0., primal - dual)
            if gap <= tol * max(yy, 1e-16) and kkt <= np.sqrt(tol) * max(alpha, 1e-12):
                converged = True
                break
    return beta, dict(converged=converged, sweeps=iteration,
                      dual_gap=gap, kkt_error=kkt,
                      objective='squared_error/(2*n) + alpha*l1')
