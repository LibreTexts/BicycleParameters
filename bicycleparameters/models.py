import warnings

import numpy as np
import matplotlib.pyplot as plt

from .bicycle import benchmark_par_to_canonical, ab_matrix, sort_modes


class Meijaard2007Model(object):
    """Whipple-Carvallo model presented in [Meijaard2007]_. It is both linear
    and the minimal model in terms of states and coordinates that fully
    describe the vehicles dynamics.

    References
    ==========

    .. [Meijaard2007] Meijaard J.P, Papadopoulos Jim M, Ruina Andy and Schwab
       A.L, 2007, Linearized dynamics equations for the balance and steer of a
       bicycle: a benchmark and review, Proc. R. Soc. A., 463:1955–1982
       http://doi.org/10.1098/rspa.2007.1857

    """

    def __init__(self, benchmark_parameter_set):
        """Initializes the model with the provided parameters.

        Parameters
        ==========
        benchmark_parameters : dictionary
            Dictionary that maps floats to the parameter keys containing:

            - ``IBxx`` : x moment of inertia of the frame/rider [kg*m**2]
            - ``IBxz`` : xz product of inertia of the frame/rider [kg*m**2]
            - ``IBzz`` : z moment of inertia of the frame/rider [kg*m**2]
            - ``IFxx`` : x moment of inertia of the front wheel [kg*m**2]
            - ``IFyy`` : y moment of inertia of the front wheel [kg*m**2]
            - ``IHxx`` : x moment of inertia of the handlebar/fork [kg*m**2]
            - ``IHxz`` : xz product of inertia of the handlebar/fork [kg*m**2]
            - ``IHzz`` : z moment of inertia of the handlebar/fork [kg*m**2]
            - ``IRxx`` : x moment of inertia of the rear wheel [kg*m**2]
            - ``IRyy`` : y moment of inertia of the rear wheel [kg*m**2]
            - ``c`` : trail [m]
            - ``g`` : acceleration due to gravity [m/s**2]
            - ``lam`` : steer axis tilt [rad]
            - ``mB`` : frame/rider mass [kg]
            - ``mF`` : front wheel mass [kg]
            - ``mH`` : handlebar/fork assembly mass [kg]
            - ``mR`` : rear wheel mass [kg]
            - ``rF`` : front wheel radius [m]
            - ``rR`` : rear wheel radius [m]
            - ``w`` : wheelbase [m]
            - ``xB`` : x distance to the frame/rider center of mass [m]
            - ``xH`` : x distance to the frame/rider center of mass [m]
            - ``zB`` : z distance to the frame/rider center of mass [m]
            - ``zH`` : z distance to the frame/rider center of mass [m]

        """
        self.parameter_set = benchmark_parameter_set

    def _parse_parameter_overrides(self, **parameter_overrides):

        par = self.parameter_set.parameters.copy()

        found_one = False
        array_key = None
        array_val = None
        for key, val in parameter_overrides.items():
            if key not in par.keys():  # don't add invalid keys
                msg = '{} is not a valid parameter, ignoring'
                warnings.warn(msg.format(key))
            else:
                if np.isscalar(val):
                    par[key] = float(val)
                else:  # is an array
                    # TODO : It would be useful if more than one can be an
                    # array. As long as the arrays are the same length you
                    # could doe this. For example this is helpful for gain
                    # scheduling multiple gains across speeds.
                    if found_one:
                        msg = 'Only 1 parameter can be an array of values.'
                        raise ValueError(msg)
                    # pass v and g through if arrays
                    elif key == 'v' or key == 'g':
                        par[key] = val
                        array_key = key
                        found_one = True
                    else:
                        array_key = key
                        array_val = val
                        found_one = True

        return par, array_key, array_val

    def form_reduced_canonical_matrices(self, **parameter_overrides):
        """Returns the canonical speed and gravity independent matrices for the
        Whipple-Carvallo bicycle model linearized about the nominal
        configuration.

        Returns
        =======
        M : ndarray, shape(2,2) or shape(n,2,2)
            Mass matrix.
        C1 : ndarray, shape(2,2) or shape(n,2,2)
            Velocity independent damping matrix.
        K0 : ndarray, shape(2,2) or shape(n,2,2)
            Gravity independent part of the stiffness matrix.
        K2 : ndarray, shape(2,2) or shape(n,2,2)
            Velocity squared independent part of the stiffness matrix.

        Notes
        =====

        The canonical matrices complete the following equation:

            M*q'' + v*C1*q' + [g*K0 + v**2*K2]*q = f

        where:

            q = [phi, delta]
            f = [Tphi, Tdelta]

        ``phi``
            Bicycle roll angle.
        ``delta``
            Steer angle.
        ``Tphi``
            Roll torque.
        ``Tdelta``
            Steer torque.
        ``v``
            Bicylce longitudinal speed.
        ``g``
            Acceleration due to gravity.

        """
        par, array_key, array_val = self._parse_parameter_overrides(
            **parameter_overrides)

        if array_val is not None:
            M = np.zeros((len(array_val), 2, 2))
            C1 = np.zeros((len(array_val), 2, 2))
            K0 = np.zeros((len(array_val), 2, 2))
            K2 = np.zeros((len(array_val), 2, 2))
            for i, val in enumerate(array_val):
                par[array_key] = val
                M[i], C1[i], K0[i], K2[i] = benchmark_par_to_canonical(par)
            return M, C1, K0, K2
        else:
            return benchmark_par_to_canonical(par)

    def form_state_space_matrices(self, **parameter_overrides):
        """Returns the A and B matrices for the Whipple model linearized about
        the upright constant velocity configuration.

        Parameters
        ==========
        speed : float
            The speed of the bicycle.

        Returns
        =======
        A : ndarray, shape(4,4)
            The state matrix.
        B : ndarray, shape(4,2)
            The input matrix.

        Notes
        =====
        ``A`` and ``B`` describe the Whipple model in state space form:

            x' = A * x + B * u

        where

        The states are [roll angle,
                        steer angle,
                        roll rate,
                        steer rate]

        The inputs are [roll torque,
                        steer torque]

        """
        if 'g' in parameter_overrides.keys():
            g = parameter_overrides['g']
        else:
            g = self.parameter_set.parameters['g']

        if 'v' in parameter_overrides.keys():
            v = parameter_overrides['v']
        else:
            v = self.parameter_set.parameters['v']

        M, C1, K0, K2 = self.form_reduced_canonical_matrices(
            **parameter_overrides)

        if len(M.shape) == 3:  # one of the parameters (not v or g) is an array
            A = np.zeros((M.shape[0], 4, 4))
            B = np.zeros((M.shape[0], 4, 2))
            for i, (Mi, C1i, K0i, K2i) in enumerate(zip(M, C1, K0, K2)):
                A[i], B[i] = ab_matrix(Mi, C1i, K0i, K2i, v, g)
        elif not isinstance(v, float):
            A = np.zeros((len(v), 4, 4))
            B = np.zeros((len(v), 4, 2))
            for i, vi in enumerate(v):
                A[i], B[i] = ab_matrix(M, C1, K0, K2, vi, g)
        elif not isinstance(g, float):
            A = np.zeros((len(g), 4, 4))
            B = np.zeros((len(g), 4, 2))
            for i, gi in enumerate(g):
                A[i], B[i] = ab_matrix(M, C1, K0, K2, v, gi)
        else:  # scalar parameters
            A, B = ab_matrix(M, C1, K0, K2, v, g)

        return A, B

    def calc_eigen(self, left=False, **parameter_overrides):
        """Returns the eigenvalues and eigenvectors of the model.

        Parameters
        ==========
        left : boolean, optional
            If true, the left eigenvectors will be returned, i.e. A.T*v=lam*v.

        Returns
        =======
        evals : ndarray, shape(4,) or shape (n, 4)
            eigenvalues
        evecs : ndarray, shape(4,4) or shape (n, 4, 4)
            eigenvectors

        """
        A, B = self.form_state_space_matrices(**parameter_overrides)

        if len(A.shape) == 3:  # array version
            m, n = 4, A.shape[0]
            evals = np.zeros((n, m), dtype='complex128')
            evecs = np.zeros((n, m, m), dtype='complex128')
            for i, Ai in enumerate(A):
                if left:
                    Ai = Ai.T
                w, v = np.linalg.eig(Ai)
                evals[i] = w
                evecs[i] = v
            return evals, evecs
        else:
            if left:
                A = A.T
            return np.linalg.eig(A)

    def calc_modal_controllability(self, **parameter_overrides):
        """Returns the modal controllability measures.

        A. M. A. Hamdan and A. H. Nayfeh, “Measures of modal controllability
        and observability for first- and second-order linear systems,” Journal
        of Guidance, Control, and Dynamics, vol. 12, no. 3, pp. 421–428, 1989,
        doi: 10.2514/3.20424.

        """

        A, B = self.form_state_space_matrices(**parameter_overrides)
        evals, evecs = self.calc_eigen(left=True, **parameter_overrides)

        def mod_cont(q, b):
            num = np.abs(np.dot(q, b))
            den = np.linalg.norm(q) * np.linalg.norm(b)
            return np.arccos(np.real(num/den))

        if len(A.shape) == 3:  # array version
            m, n = 4, A.shape[0]
            mod_ctrb = np.empty((n, m, 2))
            for k, (Bk, vk) in enumerate(zip(B, evecs)):
                for i, vi in enumerate(vk.T):
                    for j, bj in enumerate(Bk.T):
                        mod_ctrb[k, i, j] = mod_cont(vi, bj)
        else:
            mod_ctrb = np.empty((evecs.shape[1], B.shape[1]))
            for i, vi in enumerate(evecs.T):
                for j, bj in enumerate(B.T):
                    mod_ctrb[i, j] = mod_cont(vi, bj)

        return mod_ctrb

    def plot_eigenvalue_parts(self, ax=None, colors=None,
                              **parameter_overrides):
        """Returns a Matplotlib axis of the real and imaginary parts of the
        eigenvalues plotted against the provided parameter.

        Parameters
        ==========
        ax : Axes
            Matplotlib axes.
        colors : sequence, len(3)
            Matplotlib colors for the weave, capsize, and caster modes.

        """

        if ax is None:
            fig, ax = plt.subplots()

        evals, evecs = self.calc_eigen(**parameter_overrides)
        wea, cap, cas = sort_modes(evals, evecs)

        for k, v in parameter_overrides.items():
            try:
                v.shape
            except AttributeError:
                pass
            else:
                speeds = v

        if colors is None:
            weave_color = 'C0'
            capsize_color = 'C1'
            caster_color = 'C2'
        else:
            weave_color = colors[0]
            capsize_color = colors[1]
            caster_color = colors[2]
        legend = ['Imaginary Weave', 'Imaginary Capsize', 'Imaginary Caster',
                  'Real Weave', 'Real Capsize', 'Real Caster']

        # imaginary components
        ax.plot(speeds, np.abs(np.imag(wea['evals'])), color=weave_color,
                label=legend[0], linestyle='--')
        ax.plot(speeds, np.abs(np.imag(cap['evals'])), color=capsize_color,
                label=legend[1], linestyle='--')
        ax.plot(speeds, np.abs(np.imag(cas['evals'])), color=caster_color,
                label=legend[2], linestyle='--')

        # x axis line
        ax.plot(speeds, np.zeros_like(speeds), 'k-', label='_nolegend_',
                linewidth=1.5)

        # plot the real parts of the eigenvalues
        ax.plot(speeds, np.real(wea['evals']), color=weave_color,
                label=legend[3])
        ax.plot(speeds, np.real(cap['evals']), color=capsize_color,
                label=legend[4])
        ax.plot(speeds, np.real(cas['evals']), color=caster_color,
                label=legend[5])

        # set labels and limits
        ax.set_ylabel('Real and Imaginary Parts of the Eigenvalue [1/s]')
        ax.set_xlim((speeds[0], speeds[-1]))

        _, array_key, _ = self._parse_parameter_overrides(
            **parameter_overrides)

        ax.set_xlabel(array_key)

        return ax
