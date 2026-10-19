"""Complete response paths and auxiliary specifications for the article appendix."""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / 'results'
TABLES = ROOT / 'output/tables'
GROUPS = {'ea': 'Euro area', 'advanced': 'Advanced own-policy economies',
          'emerging': 'Emerging own-policy economies'}
OUTCOMES = {'log_gdp': 'GDP', 'log_prices': 'Consumer prices', 'log_reer': 'REER'}
TERMS = {'total': r'$D$', 'domestic_noncb': r'$P$', 'central_bank': r'$C$',
         'foreign_official': r'$F^O$', 'domestic_bank': r'$P^B$',
         'domestic_nonbank': r'$P^N$'}
for term, label in list(TERMS.items()):
    TERMS[term + '_x_refinancing'] = label[:-1] + r'\times\widetilde r$'

def num(x):
    return f'{x:.3f}'

def prob(x):
    if pd.isna(x):
        return '--'
    return '$<0.001$' if x < .001 else f'{x:.3f}'

def table(title, header, rows, alignment, note):
    lines = [r'\begin{table}[htbp]\centering\scriptsize\setlength{\tabcolsep}{3pt}',
             r'\caption{' + title + '}', r'\begin{tabular}{' + alignment + '}',
             r'\toprule', ' & '.join(header) + r' \\', r'\midrule']
    lines += [' & '.join(map(str, row)) + r' \\' for row in rows]
    lines += [r'\bottomrule', r'\end{tabular}', r'\notes{' + note + '}',
              r'\end{table}\FloatBarrier', '']
    return '\n'.join(lines)

def main():
    TABLES.mkdir(exist_ok=True)
    lp = pd.read_csv(RESULTS / 'ml_lp.csv')
    sim = pd.read_csv(RESULTS / 'ml_simultaneous.csv')
    curves = sim[sim.family.eq('full_curves')]
    blocks = []
    for group, group_label in GROUPS.items():
        for outcome in ['log_gdp', 'log_prices']:
            rows = []
            for h in range(13):
                cells = [h]
                n = rank = None
                for term in ['domestic_noncb', 'domestic_noncb_x_refinancing']:
                    s = lp[lp['sample'].eq(group) & lp.outcome.eq(outcome) &
                           lp.horizon.eq(h) & lp.term.eq(term)].set_index('estimator')
                    a = curves[curves['sample'].eq(group) & curves.outcome.eq(outcome) &
                               curves.horizon.eq(h) & curves.term.eq(term)].iloc[0]
                    cells += [num(s.loc['minimal', 'estimate']), num(s.loc['full', 'estimate']),
                              num(s.loc['pds', 'estimate']), num(s.loc['pds', 'se']), prob(a.p_maxT)]
                    n, rank = int(s.loc['pds', 'n']), int(s.loc['pds', 'p'])
                cells += [f'{n}/{rank}']
                rows.append(cells)
            blocks.append(table(
                group_label + ': complete ' + (OUTCOMES[outcome] if outcome == 'log_gdp' else OUTCOMES[outcome].lower()) + ' ownership paths',
                ['$h$', r'$\beta^M$', r'$\beta^F$', r'$\beta^{PDS}$', 'SE',
                 r'$p_{\max}$', r'$\gamma^M$', r'$\gamma^F$', r'$\gamma^{PDS}$',
                 'SE', r'$p_{\max}$', '$N/p$'], rows, 'r' * 12,
                r'All estimates are log percentage points under the stated shock and state normalizations. '
                r'$M$ denotes minimal and $F$ full controls; both coefficients refer to resident ownership. '
                r'SE and adjusted probabilities refer to PDS; $p_{\max}$ uses the entire 168-contrast '
                r'family. $p$ is the PDS design rank. Minimal, full and PDS estimates use the same rows.'))
    (TABLES / 'complete_lp_paths.tex').write_text('\n'.join(blocks))

    var = pd.read_csv(RESULTS / 'ml_var_simultaneous.csv')
    blocks = []
    for group, group_label in GROUPS.items():
        for outcome, outcome_label in OUTCOMES.items():
            rows = []
            for h in range(13):
                cells = [h]
                for term in ['domestic_noncb', 'domestic_noncb_x_refinancing']:
                    a = var[var['sample'].eq(group) & var.outcome.eq(outcome) &
                            var.horizon.eq(h) & var.term.eq(term)].iloc[0]
                    cells += [num(a.estimate), num(a.se), prob(a.p_maxT)]
                rows.append(cells)
            first = var[var['sample'].eq(group)].iloc[0]
            blocks.append(table(
                group_label + ': complete VARX ' + outcome_label.lower() + ' paths',
                ['$h$', r'$\beta_P$', 'SE', r'$p_{\max}$', r'$\gamma_P$', 'SE', r'$p_{\max}$'],
                rows, 'r' * 7,
                f'Common support: {int(first.n):,} observations and design rank {int(first.p)} per equation. '
                r'Log percentage points; REER increases denote appreciation. Adjusted probabilities '
                r'use all 252 VARX contrasts. Future fiscal states are held fixed.'))
    rows = []
    differences = var[var['sample'].eq('advanced minus emerging')]
    for row in differences.sort_values(['outcome', 'horizon', 'term']).itertuples():
        rows.append([OUTCOMES[row.outcome], int(row.horizon),
                     r'$\beta_P$' if row.term == 'domestic_noncb' else r'$\gamma_P$',
                     num(row.estimate), num(row.se), prob(row.p_value), prob(row.p_maxT)])
    blocks.append(table(
        'VARX advanced-minus-emerging differences: all reporting contrasts',
        ['Outcome', '$h$', 'Term', 'Difference', 'SE', '$p$', r'$p_{\max}$'],
        rows, 'lrlrrrr',
        r'Calendar-aligned influence scores retain covariance across the two groups. '
        r'The eighteen group differences are included in the complete 252-contrast VARX family.'))
    (TABLES / 'complete_var_paths.tex').write_text('\n'.join(blocks))

    sector = pd.read_csv(RESULTS / 'fiscal_sectors.csv')
    benchmark_sim = pd.read_csv(RESULTS / 'fiscal_simultaneous.csv')
    sector_adj = benchmark_sim[benchmark_sim.family.eq('creditor_sectors')]
    adj = {(r.model, r.outcome, int(r.horizon), r.term): r.p_maxT
           for r in sector_adj.itertuples()}
    titles = {
        'foreign_official_control_ownership': 'Foreign official control, ownership only',
        'foreign_official_control_rollover': 'Foreign official control and refinancing',
        'banks_nonbanks_ownership': 'Resident banks and nonbanks, ownership only',
        'banks_nonbanks_rollover': 'Resident banks and nonbanks with refinancing'}
    blocks = []
    for model, title in titles.items():
        for outcome in ['log_gdp', 'log_prices']:
            rows = []
            subset = sector[sector.model.eq(model) & sector.outcome.eq(outcome)]
            for row in subset.sort_values(['horizon', 'term']).itertuples():
                rows.append([int(row.horizon), TERMS[row.term], num(row.estimate), num(row.se),
                             prob(row.p_value), prob(adj.get((model, outcome, int(row.horizon), row.term))),
                             f'{int(row.n)}/{int(row.p)}'])
            blocks.append(table(
                title + ': ' + (OUTCOMES[outcome] if outcome == 'log_gdp' else OUTCOMES[outcome].lower()),
                ['$h$', 'Monetary exposure', 'Estimate', 'SE', '$p$', r'$p_{\max}$', '$N/p$'],
                rows, 'rlrrrrr',
                r'Full-control own-policy benchmark. $F^O$ denotes foreign official holdings, '
                r'$P^B$ resident banks, and $P^N$ resident nonbanks outside the central bank. '
                r'The reference offset is foreign nonofficial holdings. A dash marks a coefficient '
                r'outside the 36-contrast sector family; all listed pointwise results remain reported.'))
    (TABLES / 'complete_sector_results.tex').write_text('\n'.join(blocks))

    rows = []
    for row in benchmark_sim[benchmark_sim.family.eq('ownership_benchmark')].itertuples():
        rows.append([{'ea': 'Euro area', 'advanced': 'Advanced', 'emerging': 'Emerging'}[row.sample],
                     OUTCOMES[row.outcome], int(row.horizon), num(row.estimate), num(row.se),
                     prob(row.p_value), prob(row.p_maxT), f'{int(row.n)}/{int(row.p)}'])
    (TABLES / 'complete_ownership_benchmark.tex').write_text(table(
        'Matched ownership-only benchmark: all reporting contrasts',
        ['Setting', 'Outcome', '$h$', r'$\beta_P$', 'SE', '$p$', r'$p_{\max}$', '$N/p$'],
        rows, 'llrrrrrr',
        r'The full-control benchmark omits the refinancing interactions on matched support. '
        r'Adjusted probabilities use its eighteen-contrast family and are distinct from PDS inference.'))
    print('Complete LP, VARX, sector and ownership-only tables written.')

if __name__ == '__main__':
    main()
