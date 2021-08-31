"""A general function for computing a model's steady state variables and parameters values"""

import numpy as np
import scipy.optimize as opt
from copy import deepcopy
from functools import partial

from .support import compute_target_values, extract_multivariate_initial_values_and_bounds,\
    extract_univariate_initial_values_or_bounds, constrained_multivariate_residual, run_consistency_check,\
    subset_helper_block_unknowns, instantiate_steady_state_mutable_kwargs
from .classes import SteadyStateDict
from ..utilities import solvers, graph, misc
from ..blocks.parent import Parent


# Find the steady state solution
def steady_state(blocks, calibration, unknowns, targets, dissolve=None,
                 sort_blocks=True, helper_blocks=None, helper_targets=None,
                 consistency_check=True, ttol=2e-12, ctol=1e-9,
                 block_kwargs=None, verbose=False, solver=None, solver_kwargs=None,
                 constrained_method="linear_continuation", constrained_kwargs=None):
    """
    For a given model (blocks), calibration, unknowns, and targets, solve for the steady state values.

    blocks: `list`
        A list of blocks, which include the types: SimpleBlock, HetBlock, SolvedBlock, CombinedBlock
    calibration: `dict`
        The pre-specified values of variables/parameters provided to the steady state computation
    unknowns: `dict`
        A dictionary mapping unknown variables to either initial values or bounds to be provided to the numerical solver
    targets: `dict`
        A dictionary mapping target variables to desired numerical values, other variables solved for along the DAG
    dissolve: `list`
        A list of blocks, either SolvedBlock or CombinedBlock, where block-level unknowns are removed and subsumed
        by the top-level unknowns, effectively removing the "solve" components of the blocks
    sort_blocks: `bool`
        Whether the blocks need to be topologically sorted (only False when this function is called from within a
        Block object, like CombinedBlock, that has already pre-sorted the blocks)
    helper_blocks: `list`
        A list of blocks that replace some of the equations in the DAG to aid steady state calculation
    helper_targets: `list`
        A list of target names that are handled by the helper blocks
    consistency_check: `bool`
        If helper blocks are a portion of the argument blocks, re-run the DAG with the computed steady state values
        without the assistance of helper blocks and see if the targets are still hit
    ttol: `float`
        The tolerance for the targets---how close the user wants the computed target values to equal the desired values
    ctol: `float`
        The tolerance for the consistency check---how close the user wants the computed target values, without the
        use of helper blocks, to equal the desired values
    block_kwargs: `dict`
        A dict of any kwargs that specify additional settings in order to evaluate block.steady_state for any
        potential Block object, e.g. HetBlocks have backward_tol and forward_tol settings that are specific to that
        Block sub-class.
    verbose: `bool`
        Display the content of optional print statements within the solver for more responsive feedback
    solver: `string`
        The name of the numerical solver that the user would like to user. Can either be a custom solver the user
        implemented, or one of the standard root-finding methods in scipy.optim.root_scalar or scipy.optim.root
    solver_kwargs: `dict`
        The keyword arguments that the user's chosen solver requires to run
    constrained_method: `str`
        When using solvers that typically only take an initial value, x0, we provide a few options for manipulating
        the solver to account for bounds when finding a solution. These methods are described in the
        constrained_multivariate_residual function
    constrained_kwargs:
        The keyword arguments that the user's chosen constrained method requires to run

    return: ss_values: `dict`
        A dictionary containing all of the pre-specified values and computed values from the steady state computation
    """

    dissolve, block_kwargs, solver_kwargs, constrained_kwargs =\
        instantiate_steady_state_mutable_kwargs(dissolve, block_kwargs, solver_kwargs, constrained_kwargs)

    # Initial setup of blocks, targets, and dictionary of steady state values to be returned
    blocks_all = blocks
    targets = {t: 0. for t in targets} if isinstance(targets, list) else targets

    ss_values = SteadyStateDict(calibration)
    unknown_keys = unknowns.keys()

    def residual(unknown_values, bypass_redirection=False):
        ss_values.update(misc.smart_zip(unknown_keys, unknown_values))

        # TODO: Later on optimize to not evaluating blocks in residual that are no longer needed due to helper
        #   block subsetting
        for block in blocks_all:
            # TODO: this is duplicate of CombinedBlock inner_dissolve, should offload to that
            inner_dissolve = [k for k in dissolve if isinstance(block, Parent) and k in block.descendants]
            outputs = block.steady_state(ss_values, hetoutput=True, dissolve=inner_dissolve,
                                         bypass_redirection=bypass_redirection, verbose=verbose, **block_kwargs)
            ss_values.update(outputs)

        return compute_target_values(targets, ss_values)

    unknowns_solved = _solve_for_unknowns(residual, unknowns, solver, solver_kwargs,
                                          constrained_method=constrained_method,
                                          constrained_kwargs=constrained_kwargs,
                                          tol=ttol, verbose=verbose)
                            
    # Check that the solution is consistent with what would come out of the DAG without the helper blocks
    if consistency_check:
        # TODO: Shouldn't the DAG be re-sorted when the helper blocks are stripped out, so it evaluates through in the
        #   correct order? The sorted DAG here is based on including the helper blocks! So simply omitting them but
        #   retaining the order that they created may not be entirely correct?
        # Add the unknowns not handled by helpers into the DAG to be checked.
        unknowns_solved.update({k: ss_values[k] for k in unknowns if k not in unknowns_solved})

        cresid = np.max(abs(residual(unknowns_solved.values(), bypass_redirection=True)))
        if cresid > ctol:
            raise RuntimeError(f"Target value residual {cresid} exceeds ctol specified for checking"
                               f" the consistency of the DAG without redirection.")

    # Update to set the solutions for the steady state values of the unknowns
    ss_values.update(unknowns_solved)

    return ss_values


# def eval_block_ss(block, calibration, toplevel_unknowns=None, dissolve=None, **kwargs):
#     """Evaluate the .ss method of a block, given a dictionary of potential arguments"""
#     if toplevel_unknowns is None:
#         toplevel_unknowns = []
#     if dissolve is None:
#         dissolve = []

#     # Add the block's internal variables as inputs, if the block has an internal attribute
#     if isinstance(calibration, dict):
#         input_arg_dict = deepcopy(calibration)
#     else:
#         input_arg_dict = {**calibration.toplevel, **calibration.internal[block.name]} if block.name in calibration.internal else calibration.toplevel

#     # Bypass the behavior for SolvedBlocks to numerically solve for their unknowns and simply evaluate them
#     # at the provided set of unknowns if included in dissolve.
#     valid_input_kwargs = misc.input_kwarg_list(block._steady_state)
#     block_unknowns_in_toplevel_unknowns = set(block.unknowns.keys()).issubset(set(toplevel_unknowns)) if hasattr(block, "unknowns") else False
#     input_kwarg_dict = {k: v for k, v in kwargs.items() if k in valid_input_kwargs}
#     if block in dissolve and "solver" in valid_input_kwargs:
#         input_kwarg_dict["solver"] = "solved"
#         input_kwarg_dict["unknowns"] = {k: v for k, v in calibration.items() if k in block.unknowns}
#     elif block not in dissolve and block_unknowns_in_toplevel_unknowns:
#         raise RuntimeError(f"The block '{block.name}' is not in the kwarg `dissolve` but its unknowns,"
#                            f" {set(block.unknowns.keys())} are a subset of the top-level unknowns,"
#                            f" {set(toplevel_unknowns)}.\n"
#                            f"If the user provides a set of top-level unknowns that subsume block-level unknowns,"
#                            f" it must be explicitly declared in `dissolve`.")

#     return block.steady_state({k: v for k, v in input_arg_dict.items() if k in block.inputs}, **input_kwarg_dict)


def _solve_for_unknowns(residual, unknowns, solver, solver_kwargs, residual_kwargs=None,
                        constrained_method="linear_continuation", constrained_kwargs=None,
                        tol=2e-12, verbose=False):
    """
    Given a residual function (constructed within steady_state) and a set of bounds or initial values for
    the set of unknowns, solve for the root.
    TODO: Implemented as a hidden method as of now because this function relies on the structure of steady_state
        specifically and will not work with a generic residual function, due to the way it currently expects residual
        to call variables not provided as arguments explicitly but that exist in its enclosing scope.

    residual: `function`
        A function to be supplied to a numerical solver that takes unknown values as arguments
        and returns computed targets.
    unknowns: `dict`
        Refer to the `steady_state` function docstring for the "unknowns" variable
    targets: `dict`
        Refer to the `steady_state` function docstring for the "targets" variable
    tol: `float`
        The absolute convergence tolerance of the computed target to the desired target value in the numerical solver
    solver: `str`
        Refer to the `steady_state` function docstring for the "solver" variable
    solver_kwargs:
        Refer to the `steady_state` function docstring for the "solver_kwargs" variable

    return: The root[s] of the residual function as either a scalar (float) or a list of floats
    """
    if residual_kwargs is None:
        residual_kwargs = {}

    scipy_optimize_uni_solvers = ["bisect", "brentq", "brenth", "ridder", "toms748", "newton", "secant", "halley"]
    scipy_optimize_multi_solvers = ["hybr", "lm", "broyden1", "broyden2", "anderson", "linearmixing", "diagbroyden",
                                    "excitingmixing", "krylov", "df-sane"]

    # Wrap kwargs into the residual function
    residual_f = partial(residual, **residual_kwargs)

    if solver is None:
        raise RuntimeError("Must provide a numerical solver from the following set: brentq, broyden, solved")
    elif solver in scipy_optimize_uni_solvers:
        initial_values_or_bounds = extract_univariate_initial_values_or_bounds(unknowns)
        result = opt.root_scalar(residual_f, method=solver, xtol=tol,
                                 **initial_values_or_bounds, **solver_kwargs)
        if not result.converged:
            raise ValueError(f"Steady-state solver, {solver}, did not converge.")
        unknown_solutions = result.root
    elif solver in scipy_optimize_multi_solvers:
        initial_values, bounds = extract_multivariate_initial_values_and_bounds(unknowns)
        # If no bounds were provided
        if not bounds:
            result = opt.root(residual_f, initial_values,
                              method=solver, tol=tol, **solver_kwargs)
        else:
            constrained_residual = constrained_multivariate_residual(residual_f, bounds, verbose=verbose,
                                                                     method=constrained_method,
                                                                     **constrained_kwargs)
            result = opt.root(constrained_residual, initial_values,
                              method=solver, tol=tol, **solver_kwargs)
        if not result.success:
            raise ValueError(f"Steady-state solver, {solver}, did not converge."
                             f" The termination status is {result.status}.")
        unknown_solutions = list(result.x)
    # TODO: Implement a more general interface for custom solvers, so we don't need to add new elifs at this level
    #  everytime a new custom solver is implemented.
    elif solver == "broyden_custom":
        initial_values, bounds = extract_multivariate_initial_values_and_bounds(unknowns)
        # If no bounds were provided
        if not bounds:
            unknown_solutions, _ = solvers.broyden_solver(residual_f, initial_values,
                                                          tol=tol, verbose=verbose, **solver_kwargs)
        else:
            constrained_residual = constrained_multivariate_residual(residual_f, bounds, verbose=verbose,
                                                                     method=constrained_method,
                                                                     **constrained_kwargs)
            unknown_solutions, _ = solvers.broyden_solver(constrained_residual, initial_values,
                                                          verbose=verbose, tol=tol, **solver_kwargs)
        unknown_solutions = list(unknown_solutions)
    elif solver == "newton_custom":
        initial_values, bounds = extract_multivariate_initial_values_and_bounds(unknowns)
        # If no bounds were provided
        if not bounds:
            unknown_solutions, _ = solvers.newton_solver(residual_f, initial_values,
                                                         tol=tol, verbose=verbose, **solver_kwargs)
        else:
            constrained_residual = constrained_multivariate_residual(residual_f, bounds, verbose=verbose,
                                                                     method=constrained_method,
                                                                     **constrained_kwargs)
            unknown_solutions, _ = solvers.newton_solver(constrained_residual, initial_values,
                                                         tol=tol, verbose=verbose, **solver_kwargs)
        unknown_solutions = list(unknown_solutions)
    else:
        raise RuntimeError(f"steady_state is not yet compatible with {solver}.")

    return dict(misc.smart_zip(unknowns.keys(), unknown_solutions))


# def _solve_for_unknowns_w_helper_blocks(residual, unknowns, targets, helper_unknowns, helper_targets,
#                                         solver, solver_kwargs, constrained_method="linear_continuation",
#                                         constrained_kwargs=None, tol=2e-12, verbose=False, fragile=False):
#     """Enhance the solver executed in _solve_for_unknowns by handling a subset of unknowns and targets
#     with helper blocks, reducing the number of unknowns that need to be numerically solved for."""
#     # Initial evaluation of the DAG at the initial values of the unknowns, including the helper blocks,
#     # to populate the `ss_values` dict with the unknown values that:
#     # a) are handled by helper blocks and b) are excludable from the main DAG
#     # and to populate `helper_outputs` with outputs handled by helpers that ought not be changed
#     unknowns_init_vals = [v if not isinstance(v, tuple) else (v[0] + v[1]) / 2 for v in unknowns.values()]
#     targets_init_vals = dict(misc.smart_zip(targets.keys(), residual(targets, unknowns.keys(), unknowns_init_vals)))
#
#     # Subset out the unknowns and targets that are not excludable from the main DAG loop
#     unknowns_non_excl = misc.dict_diff(unknowns, helper_unknowns)
#     targets_non_excl = misc.dict_diff(targets, helper_targets)
#
#     # If the `targets` that are handled by helpers and excludable from the main DAG evaluate to 0. at the set of
#     # `unknowns` initial values and the initial `calibration`, then those `targets` have been hit analytically and
#     # we can omit them and their corresponding `unknowns` in the main DAG.
#     if np.all(np.isclose([targets_init_vals[t] for t in helper_targets.keys()], 0.)):
#         unknown_solutions = _solve_for_unknowns(residual, unknowns_non_excl, targets_non_excl,
#                                                 solver, solver_kwargs,
#                                                 constrained_method=constrained_method,
#                                                 constrained_kwargs=constrained_kwargs,
#                                                 tol=tol, verbose=verbose, fragile=fragile)
#     # If targets handled by helpers and excludable from the main DAG are not satisfied then
#     # it is assumed that helper blocks merely aid in providing more accurate guesses for the DAG solution,
#     # and they remain a part of the main DAG when solving.
#     else:
#         unknown_solutions = _solve_for_unknowns(residual, unknowns, targets, solver, solver_kwargs,
#                                                 constrained_method=constrained_method,
#                                                 constrained_kwargs=constrained_kwargs,
#                                                 tol=tol, verbose=verbose, fragile=fragile)
#     return unknown_solutions
