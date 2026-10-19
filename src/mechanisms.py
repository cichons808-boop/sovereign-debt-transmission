"""Matched-support tests of two external explanations of the price interaction.

FX denomination and creditor residence measure different liabilities. The FX
state is the annual Arslanalp--Tsuda or DGM share dated before the shock. The deficit state is
minus the predetermined current account. Both shock slopes are unpenalized.
All within-setting contrasts and explicit AE-minus-EM comparisons enter one
36-member exploratory simultaneous family.
"""
import json
import hashlib
import numpy as np
import pandas as pd
from scipy.stats import t
import selection as ml
from local_projection import fit
from specification import setup
from simultaneous_inference import correct
from reporting_families import difference as group_difference


def record(f, term, label):
    j = f['coefficient_names'].index(term)
    e = next(e for e in f['estimates'] if e['term'] == term)
    return dict(sample=f['sample'], model=label, outcome=f['outcome'],
                horizon=f['horizon'], term=label, n=f['n'], p=f['p'],
                countries=f['countries'], df=f['df'], start=f['time_start'],
                end=f['time_end'], psi=np.array(f['influence_by_time'])[:, j], **{k: v for k, v in e.items() if k != 'term'})


def main():
    specification = json.loads((ml.P / 'config/mechanisms.json').read_text())
    data = ml.populations()
    fits, contrasts, support = [], [], []
    gamma = 'domestic_noncb_x_refinancing'
    for sample in specification['samples']:
        baseline, extra, core = setup(data[sample], 'rollover', True)
        augmented = baseline.copy()
        new = ['fx_denomination', 'external_deficit']
        # fiscal_data.py already divides the current-account ratio by five.
        states = [augmented.fx_share / .1, -augmented.ca_state]
        for name, state in zip(new, states):
            augmented['a_' + name] = state
            augmented['f_' + name] = augmented.mp * state
            augmented['i_' + name] = augmented['info'] * state
            for lag in [1, 2]:
                for prefix in ['f', 'i']:
                    augmented[f'{prefix}_{name}_lag{lag}'] = augmented.groupby('country')[prefix + '_' + name].shift(lag)
        # The deficit columns replace identical current-account columns; the
        # remaining baseline control space and selection rule are preserved.
        augmented_extra = [s for s in extra if not s.startswith('macro_ca_state')]
        for h in specification['horizons']:
            _, va = fit(augmented, core + new, 'rollover', 'log_prices', h,
                        additional_nuisance=augmented_extra, return_validation=True)
            matched = baseline.copy()
            matched['ea_member'] &= matched.index.isin(va['g'].index)
            _, vb = fit(matched, core, 'rollover', 'log_prices', h,
                        additional_nuisance=extra, return_validation=True)
            assert np.array_equal(va['g'].index, vb['g'].index)
            current = []
            for v, names, ex, variant in [(vb, core, extra, 'matched baseline'),
                                          (va, core + new, augmented_extra, 'FX and external balance')]:
                f = ml.estimate(v, names, ex, 'pds')
                f.update(sample=sample, model='rollover', outcome='log_prices',
                         horizon=h, variant=variant,
                         pair_sha256=hashlib.sha256(v['g'][['country', 'period']].to_csv(index=False).encode()).hexdigest())
                fits.append(f)
                current.append(f)
            b, a = current
            rb = record(b, gamma, 'matched baseline gamma')
            ra = record(a, gamma, 'augmented gamma')
            assert rb['start'] == ra['start'] and rb['end'] == ra['end']
            psi = ra['psi'] - rb['psi']
            variance = float(psi @ psi)
            for lag in range(1, min(12, len(psi) - 1) + 1):
                variance += 2 * (1 - lag / 13) * float(psi[lag:] @ psi[:-lag])
            se = np.sqrt(max(variance, 0.))
            change = ra['estimate'] - rb['estimate']
            critical = t.ppf(.975, ra['df'])
            difference = dict(ra, model='change in gamma', term='change in gamma',
                              estimate=change, se=se, ci_low=change-critical*se,
                              ci_high=change+critical*se,
                              p_value=float(2*t.sf(abs(change/se),ra['df'])), psi=psi)
            contrasts += [rb, ra, difference,
                          record(a, new[0], 'FX denomination slope'),
                          record(a, new[1], 'external deficit slope')]
            keys = va['g'][['country', 'period', 'fx_share', 'ca_state']].copy()
            keys['sample'] = sample
            keys['horizon'] = h
            support.append(keys)
            print('External mechanism checks', sample, h, 'N', a['n'],
                  'countries', a['countries'], 'gamma', rb['estimate'], ra['estimate'], flush=True)
    for h in specification['horizons']:
        for variant, label in [('matched baseline', 'baseline AE minus EM'),
                               ('FX and external balance', 'augmented AE minus EM')]:
            a = next(f for f in fits if f['sample']=='advanced' and f['horizon']==h and f['variant']==variant)
            b = next(f for f in fits if f['sample']=='emerging' and f['horizon']==h and f['variant']==variant)
            comparison = group_difference(a, b, gamma)
            comparison.update(model=label, term=label, n=a['n']+b['n'], countries=a['countries']+b['countries'])
            contrasts.append(comparison)
    assert len(contrasts) == specification['family_size']
    ml.dump(fits, 'mechanisms')
    pd.concat(support).to_csv(ml.R / 'mechanism_sample_keys.csv', index=False)
    pd.DataFrame(correct('external_mechanisms', contrasts)).to_csv(ml.R / 'mechanism_contrasts.csv', index=False)


if __name__ == '__main__':
    main()
