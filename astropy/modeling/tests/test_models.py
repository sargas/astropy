# Licensed under a 3-clause BSD style license - see LICENSE.rst

"""
Tests for model evaluation.
Compare the results of some models with other programs.
"""

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import types

try:
    import cPickle as pickle
except ImportError:
    import pickle

import numpy as np

from numpy.testing import utils

from .example_models import models_1D, models_2D
from .. import fitting, models
from ..core import (LabeledInput, SerialCompositeModel, SummedCompositeModel,
                    Fittable1DModel, Fittable2DModel)
from ..polynomial import PolynomialModel
from ...tests.helper import pytest

from ...extern import six
from ...extern.six.moves import copyreg as copy_reg

try:
    from scipy import optimize  # pylint: disable=W0611
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False


class TestSerialComposite(object):
    """
    Test composite models evaluation in series
    """
    def setup_class(self):
        self.y, self.x = np.mgrid[:5, :5]
        self.p1 = models.Polynomial1D(3)
        self.p11 = models.Polynomial1D(3)
        self.p2 = models.Polynomial2D(3)

    def test_single_array_input(self):
        model = SerialCompositeModel([self.p1, self.p11])
        result = model(self.x)
        xx = self.p11(self.p1(self.x))
        utils.assert_almost_equal(xx, result)

    def test_labeledinput_1(self):
        labeled_input = LabeledInput([self.x, self.y], ['x', 'y'])
        model = SerialCompositeModel([self.p2, self.p1],
                                     [['x', 'y'], ['z']],
                                     [['z'], ['z']])
        result = model(labeled_input)
        z = self.p2(self.x, self.y)
        z1 = self.p1(z)
        utils.assert_almost_equal(z1, result.z)

    def test_labeledinput_2(self):
        labeled_input = LabeledInput([self.x, self.y], ['x', 'y'])
        rot = models.Rotation2D(angle=23.4)
        offx = models.Shift(-2)
        offy = models.Shift(1.2)
        model = SerialCompositeModel([rot, offx, offy],
                                     [['x', 'y'], ['x'], ['y']],
                                     [['x', 'y'], ['x'], ['y']])
        result = model(labeled_input)
        x, y = rot(self.x, self.y)
        x = offx(x)
        y = offy(y)
        utils.assert_almost_equal(x, result.x)
        utils.assert_almost_equal(y, result.y)

    def test_labeledinput_3(self):
        labeled_input = LabeledInput([2, 4.5], ['x', 'y'])
        rot = models.Rotation2D(angle=23.4)
        offx = models.Shift(-2)
        offy = models.Shift(1.2)
        model = SerialCompositeModel([rot, offx, offy],
                                     [['x', 'y'], ['x'], ['y']],
                                     [['x', 'y'], ['x'], ['y']])
        result = model(labeled_input)
        x, y = rot(2, 4.5)
        x = offx(x)
        y = offy(y)
        utils.assert_almost_equal(x, result.x)
        utils.assert_almost_equal(y, result.y)

    def test_multiple_input(self):
        rot = models.Rotation2D(angle=-60)
        model = SerialCompositeModel([rot, rot])
        xx, yy = model(self.x, self.y)
        inverse_model = model.inverse()
        x1, y1 = inverse_model(xx, yy)
        utils.assert_almost_equal(x1, self.x)
        utils.assert_almost_equal(y1, self.y)


class TestSummedComposite(object):
    """
    Test composite models evaluation in parallel
    """

    def setup_class(self):
        self.x = np.linspace(1, 10, 100)
        self.y = np.linspace(1, 10, 100)
        self.p1 = models.Polynomial1D(3)
        self.p11 = models.Polynomial1D(3)
        self.p2 = models.Polynomial2D(3)
        self.p1.parameters = [1.4, 2.2, 3.1, 4]
        self.p2.c0_0 = 100

    def test_single_array_input(self):
        model = SummedCompositeModel([self.p1, self.p11])
        result = model(self.x)
        delta11 = self.p11(self.x)
        delta1 = self.p1(self.x)
        xx = delta1 + delta11
        utils.assert_almost_equal(xx, result)

    def test_labeledinput(self):
        labeled_input = LabeledInput([self.x, self.y], ['x', 'y'])
        model = SummedCompositeModel([self.p1, self.p11], inmap=['x'], outmap=['x'])
        result = model(labeled_input)
        delta11 = self.p11(self.x)
        delta1 = self.p1(self.x)
        xx = delta1 + delta11
        utils.assert_almost_equal(xx, result.x)

    def test_inputs_outputs_mismatch(self):
        p2 = models.Polynomial2D(1)
        ch2 = models.Chebyshev2D(1, 1)
        with pytest.raises(ValueError):
            SummedCompositeModel([p2, ch2])


def test_pickle():
    def reduce_method(m):
        return (getattr, (m.__self__, m.__func__.__name__))

    copy_reg.pickle(types.MethodType, reduce_method)

    p1 = models.Polynomial1D(3)
    p11 = models.Polynomial1D(4)
    g1 = models.Gaussian1D(10.3, 5.4, 1.2)
    serial_composite_model = SerialCompositeModel([p1, g1])
    parallel_composite_model = SummedCompositeModel([serial_composite_model,
                                                     p11])
    s = pickle.dumps(parallel_composite_model)
    s1 = pickle.loads(s)
    assert s1(3) == parallel_composite_model(3)


@pytest.mark.skipif('not HAS_SCIPY')
def test_custom_model(amplitude=4, frequency=1):

    def sine_model(x, amplitude=4, frequency=1):
        """
        Model function
        """
        return amplitude * np.sin(2 * np.pi * frequency * x)

    def sine_deriv(x, amplitude=4, frequency=1):
        """
        Jacobian of model function, e.g. derivative of the function with
        respect to the *parameters*
        """
        da = np.sin(2 * np.pi * frequency * x)
        df = 2 * np.pi * x * amplitude * np.cos(2 * np.pi * frequency * x)
        return np.vstack((da, df))

    SineModel = models.custom_model_1d(sine_model, func_fit_deriv=sine_deriv)

    x = np.linspace(0, 4, 50)
    sin_model = SineModel()

    y = sin_model.evaluate(x, 5., 2.)
    y_prime = sin_model.fit_deriv(x, 5., 2.)

    np.random.seed(0)
    data = sin_model(x) + np.random.rand(len(x)) - 0.5
    fitter = fitting.LevMarLSQFitter()
    model = fitter(sin_model, x, data)
    assert np.all((np.array([model.amplitude.value, model.frequency.value]) -
                   np.array([amplitude, frequency])) < 0.001)


def test_custom_model_init():
    @models.custom_model_1d
    def SineModel(x, amplitude=4, frequency=1):
        """
        Model function
        """
        return amplitude * np.sin(2 * np.pi * frequency * x)

    sin_model = SineModel(amplitude=2., frequency=0.5)
    assert sin_model.amplitude == 2.
    assert sin_model.frequency == 0.5


def test_custom_model_defaults():
    @models.custom_model_1d
    def SineModel(x, amplitude=4, frequency=1):
        """
        Model function
        """
        return amplitude * np.sin(2 * np.pi * frequency * x)

    sin_model = SineModel()
    assert SineModel.amplitude.default == 4
    assert SineModel.frequency.default == 1

    assert sin_model.amplitude == 4
    assert sin_model.frequency == 1


class Fittable2DModelTester(object):
    """
    Test class for all two dimensional parametric models.

    Test values have to be defined in example_models.py. It currently test the model
    with different input types, evaluates the model at different positions and
    assures that it gives the correct values. And tests if the  model works with
    the NonLinearFitter.

    This can be used as a base class for user defined model testing.
    """
    def setup_class(self):
        self.N = 100
        self.M = 100
        self.eval_error = 0.0001
        self.fit_error = 0.1
        self.x = 5.3
        self.y = 6.7
        self.x1 = np.arange(1, 10, .1)
        self.y1 = np.arange(1, 10, .1)
        self.y2, self.x2 = np.mgrid[:10, :8]

    def test_input2D(self, model_class, test_parameters):
        """
        Test model with different input types.
        """
        model = create_model(model_class, test_parameters)
        model(self.x, self.y)
        model(self.x1, self.y1)
        model(self.x2, self.y2)

    def test_eval2D(self, model_class, test_parameters):
        """
        Test model values add certain given points
        """
        model = create_model(model_class, test_parameters)
        x = test_parameters['x_values']
        y = test_parameters['y_values']
        z = test_parameters['z_values']
        assert np.all((np.abs(model(x, y) - z) < self.eval_error))

    @pytest.mark.skipif('not HAS_SCIPY')
    def test_fitter2D(self, model_class, test_parameters):
        """
        Test if the parametric model works with the fitter.
        """
        x_lim = test_parameters['x_lim']
        y_lim = test_parameters['y_lim']

        parameters = test_parameters['parameters']
        model = create_model(model_class, test_parameters)

        if isinstance(parameters, dict):
            parameters = [parameters[name] for name in model.param_names]

        if "log_fit" in test_parameters:
            if test_parameters['log_fit']:
                x = np.logspace(x_lim[0], x_lim[1], self.N)
                y = np.logspace(y_lim[0], y_lim[1], self.N)
        else:
            x = np.linspace(x_lim[0], x_lim[1], self.N)
            y = np.linspace(y_lim[0], y_lim[1], self.N)
        xv, yv = np.meshgrid(x, y)

        np.random.seed(0)
        # add 10% noise to the amplitude
        noise = np.random.rand(self.N, self.N) - 0.5
        data = model(xv, yv) + 0.1 * parameters[0] * noise
        fitter = fitting.LevMarLSQFitter()
        new_model = fitter(model, xv, yv, data)

        params = [getattr(new_model, name) for name in new_model.param_names]
        fixed = [param.fixed for param in params]
        expected = np.array([val for val, fixed in zip(parameters, fixed)
                             if not fixed])
        fitted = np.array([param.value for param in params
                           if not param.fixed])
        utils.assert_allclose(fitted, expected,
                              atol=self.fit_error)

    @pytest.mark.skipif('not HAS_SCIPY')
    def test_deriv_2D(self, model_class, test_parameters):
        """
        Test the derivative of a model by fitting with an estimated and
        analytical derivative
        """
        x_lim = test_parameters['x_lim']
        y_lim = test_parameters['y_lim']

        if model_class.fit_deriv is None:
            pytest.skip("Derivative function is not defined for model.")
        if issubclass(model_class, (models.PolynomialModel, models.OrthoPolynomialBase)):
            pytest.skip("Skip testing derivative of polynomials.")

        if "log_fit" in test_parameters:
            if test_parameters['log_fit']:
                x = np.logspace(x_lim[0], x_lim[1], self.N)
                y = np.logspace(y_lim[0], y_lim[1], self.M)
        else:
            x = np.linspace(x_lim[0], x_lim[1], self.N)
            y = np.linspace(y_lim[0], y_lim[1], self.M)
        xv, yv = np.meshgrid(x, y)

        try:
            model_with_deriv = create_model(model_class, test_parameters,
                                    use_constraints=False, parameter_key='deriv_initial')
            model_no_deriv = create_model(model_class, test_parameters,
                                    use_constraints=False, parameter_key='deriv_initial')
            model = create_model(model_class, test_parameters, use_constraints=False,
                                 parameter_key='deriv_initial')
        except KeyError:
            model_with_deriv = create_model(model_class, test_parameters, use_constraints=False)
            model_no_deriv = create_model(model_class, test_parameters, use_constraints=False)
            model = create_model(model_class, test_parameters, use_constraints=False)

        # add 10% noise to the amplitude
        rsn = np.random.RandomState(1234567890)
        n = 0.1 * test_parameters['parameters'][0] * (rsn.rand(self.M, self.N) - 0.5)

        data = model(xv, yv) + n
        fitter_with_deriv = fitting.LevMarLSQFitter()
        new_model_with_deriv = fitter_with_deriv(model_with_deriv, xv, yv, data)
        fitter_no_deriv = fitting.LevMarLSQFitter()
        new_model_no_deriv = fitter_no_deriv(model_no_deriv, xv, yv, data, estimate_jacobian=True)
        utils.assert_allclose(new_model_with_deriv.parameters, new_model_no_deriv.parameters,
                              rtol=0.1)


class Fittable1DModelTester(object):
    """
    Test class for all one dimensional parametric models.

    Test values have to be defined in example_models.py. It currently test the model
    with different input types, evaluates the model at different positions and
    assures that it gives the correct values. And tests if the  model works with
    the NonLinearFitter.

    This can be used as a base class for user defined model testing.
    """

    def setup_class(self):
        self.N = 100
        self.M = 100
        self.eval_error = 0.0001
        self.fit_error = 0.1
        self.x = 5.3
        self.y = 6.7
        self.x1 = np.arange(1, 10, .1)
        self.y1 = np.arange(1, 10, .1)
        self.y2, self.x2 = np.mgrid[:10, :8]

    def test_input1D(self, model_class, test_parameters):
        """
        Test model with different input types.
        """
        model = create_model(model_class, test_parameters)
        model(self.x)
        model(self.x1)
        model(self.x2)

    def test_dict(self, model_class, test_parameters):
        """
        Test type of test_parameters and model_class
        """
        assert type(test_parameters) == dict

    def test_eval1D(self, model_class, test_parameters):
        """
        Test model values at certain given points
        """
        model = create_model(model_class, test_parameters)
        x = test_parameters['x_values']
        y = test_parameters['y_values']
        utils.assert_allclose(model(x), y, atol=self.eval_error)

    @pytest.mark.skipif('not HAS_SCIPY')
    def test_fitter1D(self, model_class, test_parameters):
        """
        Test if the parametric model works with the fitter.
        """
        x_lim = test_parameters['x_lim']
        parameters = test_parameters['parameters']
        model = create_model(model_class, test_parameters)

        if isinstance(parameters, dict):
            parameters = [parameters[name] for name in model.param_names]

        if "log_fit" in test_parameters:
            if test_parameters['log_fit']:
                x = np.logspace(x_lim[0], x_lim[1], self.N)
        else:
            x = np.linspace(x_lim[0], x_lim[1], self.N)

        np.random.seed(0)
        # add 10% noise to the amplitude
        relative_noise_amplitude = 0.01
        data = (1 + relative_noise_amplitude * np.random.randn(len(x))) * model(x)
        fitter = fitting.LevMarLSQFitter()
        new_model = fitter(model, x, data)

        # Only check parameters that were free in the fit
        params = [getattr(new_model, name) for name in new_model.param_names]
        fixed = [param.fixed for param in params]
        expected = np.array([val for val, fixed in zip(parameters, fixed)
                             if not fixed])
        fitted = np.array([param.value for param in params
                           if not param.fixed])
        utils.assert_allclose(fitted, expected, atol=self.fit_error)

    @pytest.mark.skipif('not HAS_SCIPY')
    def test_deriv_1D(self, model_class, test_parameters):
        """
        Test the derivative of a model by comparing results with an estimated derivative
        """
        x_lim = test_parameters['x_lim']

        if model_class.fit_deriv is None:
            pytest.skip("Derivative function is not defined for model.")
        if issubclass(model_class, (models.PolynomialModel, models.OrthoPolynomialBase)):
            pytest.skip("Skip testing derivative of polynomials.")

        if "log_fit" in test_parameters:
            if test_parameters['log_fit']:
                x = np.logspace(x_lim[0], x_lim[1], self.N)
        else:
            x = np.linspace(x_lim[0], x_lim[1], self.N)

        parameters = test_parameters['parameters']
        model_with_deriv = create_model(model_class, test_parameters, use_constraints=False)
        model_no_deriv = create_model(model_class, test_parameters, use_constraints=False)

        # add 10% noise to the amplitude
        rsn = np.random.RandomState(1234567890)
        n = 0.1 * parameters[0] * (rsn.rand(self.N) - 0.5)

        data = model_with_deriv(x) + n
        fitter_with_deriv = fitting.LevMarLSQFitter()
        new_model_with_deriv = fitter_with_deriv(model_with_deriv, x, data)
        fitter_no_deriv = fitting.LevMarLSQFitter()
        new_model_no_deriv = fitter_no_deriv(model_no_deriv, x, data, estimate_jacobian=True)
        utils.assert_allclose(new_model_with_deriv.parameters, new_model_no_deriv.parameters, atol=0.1)


def create_model(model_class, test_parameters, use_constraints=True, parameter_key='parameters'):
    """
    Create instance of model class.
    """

    constraints = {}
    if issubclass(model_class, Fittable1DModel) or issubclass(model_class, Fittable2DModel):
        if "requires_scipy" in test_parameters and not HAS_SCIPY:
            pytest.skip("SciPy not found")
        if use_constraints:
            if 'constraints' in test_parameters:
                constraints = test_parameters['constraints']
        return model_class(*test_parameters[parameter_key], **constraints)
    elif issubclass(model_class, PolynomialModel):
        return model_class(**test_parameters[parameter_key])


@pytest.mark.parametrize(('model_class', 'test_parameters'), list(models_1D.items()))
class TestFittable1DModels(Fittable1DModelTester):
    pass


@pytest.mark.parametrize(('model_class', 'test_parameters'), list(models_2D.items()))
class TestFittable2DModels(Fittable2DModelTester):
    pass


def test_ShiftModel():
    # Shift by a scalar
    m = models.Shift(42)
    assert m(0) == 42
    utils.assert_equal(m([1, 2]), [43, 44])

    # Shift by a list
    m = models.Shift([42, 43], n_models=2)
    utils.assert_equal(m(0), [42, 43])
    utils.assert_equal(m([1, 2], model_set_axis=False),
                       [[ 43,  44], [ 44,  45]])


def test_ScaleModel():
    # Scale by a scalar
    m = models.Scale(42)
    assert m(0) == 0
    utils.assert_equal(m([1, 2]), [42, 84])

    # Scale by a list
    m = models.Scale([42, 43], n_models=2)
    utils.assert_equal(m(0), [0, 0])
    utils.assert_equal(m([1, 2], model_set_axis=False),
                       [[ 42,  84], [ 43,  86]])


def test_parametric_model_repr():
    """Some unit tests that cover lines in core.py that are untested at the
    moment"""

    m = models.Gaussian1D(1, 2, 3)
    assert repr(m) == '<Gaussian1D(amplitude=1.0, mean=2.0, stddev=3.0)>'
