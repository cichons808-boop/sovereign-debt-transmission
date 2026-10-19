"""Independent numerical checks of the explicit estimation algorithms."""
import json
import numpy as np
from lasso import coordinate_descent
import selection as ml
from local_projection import fit
from specification import setup


def independent_proximal_lasso(x, y, alpha):
    """FISTA check using a full-vector proximal gradient, not coordinates."""
    gram = x.T @ x / len(y)
    xy = x.T @ y / len(y)
    lipschitz = float(np.linalg.eigvalsh(gram)[-1])
    b = z = np.zeros(x.shape[1])
    momentum = 1.
    for iteration in range(30000):
        step = z + (xy - gram @ z) / lipschitz
        new = np.sign(step) * np.maximum(abs(step) - alpha / lipschitz, 0.)
        acceleration = (1 + np.sqrt(1 + 4 * momentum * momentum)) / 2
        extrapolation = new + (momentum - 1) / acceleration * (new - b)
        change = np.max(abs(new - b))
        b, z, momentum = new, extrapolation, acceleration
        if change < 1e-12:
            break
    return b


def lasso_checks():
    rng = np.random.default_rng(20261019)
    n, p = 400, 25
    q, _ = np.linalg.qr(rng.normal(size=(n, p)))
    x = q * np.sqrt(n)
    y = x @ np.r_[1., -.8, .4, np.zeros(p-3)] + rng.normal(size=n)
    alpha = .08
    b, diagnostics = coordinate_descent(x, y, alpha)
    xy = x.T @ y / n
    exact = np.sign(xy) * np.maximum(abs(xy) - alpha, 0.)
    closed_form_error = float(np.max(abs(b - exact)))
    assert closed_form_error < 1e-10 and diagnostics['converged']
    x[:, 1:] += .55 * x[:, [0]]
    b, diagnostics = coordinate_descent(x, y, alpha)
    check = independent_proximal_lasso(x, y, alpha)
    proximal_error = float(np.max(abs(b - check)))
    assert proximal_error < 1e-7 and diagnostics['converged']
    assert diagnostics['dual_gap'] < 1e-9
    return dict(orthogonal_closed_form_max_error=closed_form_error,
                independent_proximal_max_error=proximal_error,
                coordinate_dual_gap=diagnostics['dual_gap'],
                coordinate_kkt_error=diagnostics['kkt_error'])


def actual_design_checks():
    populations = ml.populations()
    saved = json.loads((ml.R / 'ml_lp.json').read_text())
    errors, covariance_errors, keys = [], [], []
    for sample in ['ea', 'advanced', 'emerging']:
        d, ex, names = setup(populations[sample], 'rollover', sample != 'ea')
        for outcome in ['log_gdp', 'log_prices']:
            for h in [4, 8, 12]:
                _, v = fit(d, names, 'rollover', outcome, h,
                           additional_nuisance=ex, return_validation=True)
                c, q, rank, w, wr, labels, _ = ml.designs(v, names, ex)
                for method in ['minimal', 'full', 'pds']:
                    f = next(f for f in saved if f['sample'] == sample and f['estimator'] == method
                             and f['outcome'] == outcome and f['horizon'] == h)
                    chosen = np.array([label in f['selected_labels'] for label in labels])
                    cc = np.column_stack([c, w[:, chosen]])
                    cc, _, _, _ = ml.independent(cc)
                    design = np.column_stack([cc, v['F']])
                    scales = np.linalg.norm(design, axis=0)
                    direct = np.linalg.lstsq(design/scales, v['Y'], rcond=None)[0]/scales
                    residual = v['Y']-design@direct
                    coefficient_error = float(np.max(abs(direct[-len(names):]-f['beta'])))
                    # SVD residualization provides a second nuisance projection.
                    z = v['F']-cc@np.linalg.lstsq(cc, v['F'], rcond=None)[0]
                    bread = np.linalg.solve(z.T@z, np.eye(len(names)))
                    ti = v['g'].time_index.to_numpy(int)
                    scores = np.zeros((ti.max()-ti.min()+1, len(names)))
                    np.add.at(scores, ti-ti.min(), z*residual[:, None])
                    distance = abs(np.arange(len(scores))[:, None]-np.arange(len(scores))[None, :])
                    kernel = np.maximum(1-distance/13, 0.)
                    periods = v['g'].time_index.nunique()
                    factor = periods/(periods-1)*(len(ti)-1)/(len(ti)-f['p'])
                    covariance = bread@(scores.T@kernel@scores)@bread*factor
                    covariance_error = float(np.max(abs(covariance-np.array(f['covariance_HAC']))))
                    assert coefficient_error < 1e-7, (sample, outcome, h, method, coefficient_error)
                    assert covariance_error < 1e-6, (sample, outcome, h, method, covariance_error)
                    errors.append(coefficient_error)
                    covariance_errors.append(covariance_error)
                    keys.append(dict(sample=sample, outcome=outcome, horizon=h, estimator=method,
                                     coefficient_max_error=coefficient_error, covariance_max_error=covariance_error))
    return dict(designs_checked=len(keys), full_SVD_coefficient_max_error=max(errors),
                dense_Bartlett_covariance_max_error=max(covariance_errors), checks=keys)


def main():
    result = dict(status='passed', lasso=lasso_checks(), regression=actual_design_checks(),
                  high_level_estimator_dependency=False)
    (ml.R/'engine_validation.json').write_text(json.dumps(result, indent=2)+'\n')
    print('Matrix-engine verification passed:', result['regression']['designs_checked'], 'actual designs', flush=True)


if __name__ == '__main__':
    main()
