"""Fixtures used by tests."""

import pytest

from sequence_jacobian import steady_state
from sequence_jacobian.models import rbc, krusell_smith, hank, two_asset


@pytest.fixture(scope='session')
def rbc_model():
    blocks = [rbc.household, rbc.mkt_clearing, rbc.firm, rbc.steady_state_solution]
    unknowns = {"beta": None, "vphi": None}
    targets = {"goods_mkt": 0, "euler": 0}
    calibration = {"eis": 1, "delta": 0.025, "alpha": 0.11, "frisch": 1., "L": 1.0, "r": 0.01}
    ss = steady_state(blocks, calibration, unknowns, targets, solver="solved", consistency_check=True)
    return blocks, unknowns, targets, calibration, ss


@pytest.fixture(scope='session')
def krusell_smith_model():
    blocks = [krusell_smith.household, krusell_smith.firm, krusell_smith.mkt_clearing, krusell_smith.income_state_vars,
              krusell_smith.asset_state_vars, krusell_smith.firm_steady_state_solution]
    unknowns = {"beta": (0.98/1.01, 0.999/1.01)}
    targets = {"K": "A"}
    calibration = {"eis": 1, "delta": 0.025, "alpha": 0.11, "rho": 0.966, "sigma": 0.5, "L": 1.0,
                   "nS": 2, "nA": 10, "amax": 200, "r": 0.01}
    ss = steady_state(blocks, calibration, unknowns, targets, solver="brentq", consistency_check=True, full_output=True)
    return blocks, unknowns, targets, calibration, ss


@pytest.fixture(scope='session')
def one_asset_hank_model():
    blocks = [hank.household_trans, hank.firm, hank.monetary, hank.fiscal, hank.mkt_clearing, hank.nkpc,
              hank.income_state_vars, hank.asset_state_vars, hank.partial_steady_state_solution]
    unknowns = {"beta": 0.986, "vphi": 0.8}
    targets = {"asset_mkt": 0, "labor_mkt": 0}
    calibration = {"r": 0.005, "rstar": 0.005, "eis": 0.5, "frisch": 0.5, "mu": 1.2, "B_Y": 5.6,
                   "rho_s": 0.966, "sigma_s": 0.5, "kappa": 0.1, "phi": 1.5, "Y": 1, "Z": 1, "L": 1,
                   "pi": 0, "nS": 2, "amax": 150, "nA": 10, "div_rule": None, "tax_rule": None}
    ss = steady_state(blocks, calibration, unknowns, targets, solver="broyden", consistency_check=True, noisy=False)
    return blocks, unknowns, targets, calibration, ss


@pytest.fixture(scope='session')
def two_asset_hank_model():
    blocks = [two_asset.household_inc, two_asset.make_grids, two_asset.pricing, two_asset.arbitrage,
              two_asset.labor, two_asset.investment, two_asset.dividend, two_asset.taylor, two_asset.fiscal,
              two_asset.finance, two_asset.wage, two_asset.union, two_asset.mkt_clearing,
              two_asset.adjustment_costs, two_asset.partial_steady_state_solution]
    unknowns = {"beta": 0.976, "vphi": 2.07, "chi1": 6.5}
    targets = {"asset_mkt": 0, "labor_mkt": 0, "B": "Bh"}
    calibration = {"pi": 0, "piw": 0, "Q": 1, "Y": 1, "N": 1, "r": 0.0125, "rstar": 0.0125, "i": 0.0125,
                   "tot_wealth": 14, "K": 10, "delta": 0.02, "kappap": 0.1, "muw": 1.1, "Bh": 1.04,
                   "Bg": 2.8, "G": 0.2, "eis": 0.5, "frisch": 1, "chi0": 0.25, "chi2": 2, "epsI": 4,
                   "omega": 0.005, "kappaw": 0.1, "phi": 1.5, "nZ": 3, "nB": 10, "nA": 16, "nK": 4,
                   "bmax": 50, "amax": 4000, "kmax": 1, "rho_z": 0.966, "sigma_z": 0.92}
    ss = steady_state(blocks, calibration, unknowns, targets, solver="broyden", consistency_check=True, noisy=False)
    return blocks, unknowns, targets, calibration, ss
