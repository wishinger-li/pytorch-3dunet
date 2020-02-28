from io import BytesIO
from pathlib import Path

import h5py
import numpy
import pytest
import torch

from pybio.core.transformations import apply_transformations
from pybio.spec import load_model
from pybio.spec.utils import get_instance
from pytorch3dunet.unet3d.model import UNet3D


@pytest.fixture
def dummy_input():
    return [numpy.random.uniform(-2, 2, [1, 1, 144, 234, 234]).astype(numpy.float32)]


def test_dummy_input(cache_path, dummy_input):
    spec_path = (
        Path(__file__).parent / "../../bioimage-io/UNet3DArabidopsisOvules.model/UNet3DArabidopsisOvules.model.yaml"
    )
    assert spec_path.exists()

    pybio_model = load_model(str(spec_path), cache_path=cache_path)
    for dummy, spec in zip(dummy_input, pybio_model.spec.inputs):
        assert str(dummy.dtype) == spec.data_type
        assert dummy.shape == spec.shape


def test_Net3DArabidopsisOvules_forward(cache_path):
    spec_path = (
        Path(__file__).parent / "../../bioimage-io/UNet3DArabidopsisOvules.model/UNet3DArabidopsisOvules.model.yaml"
    ).resolve()
    assert spec_path.exists(), spec_path
    pybio_model = load_model(str(spec_path), cache_path=cache_path)
    assert pybio_model.spec.outputs[0].shape.reference_input == "raw"
    assert pybio_model.spec.outputs[0].shape.scale == (1, 1, 1, 1, 1)
    assert pybio_model.spec.outputs[0].shape.offset == (0, 0, 0, 0, 0)

    assert isinstance(pybio_model.spec.prediction.weights.source, BytesIO)
    assert pybio_model.spec.test_input is not None
    assert pybio_model.spec.test_input.suffix == ".npy", pybio_model.spec.test_input.suffix
    assert pybio_model.spec.test_output is not None
    assert pybio_model.spec.test_output.suffix == ".npy", pybio_model.spec.test_output.suffix


    model: torch.nn.Module = get_instance(pybio_model)
    assert isinstance(model, UNet3D)
    assert hasattr(model, "forward")
    model_weights = torch.load(pybio_model.spec.prediction.weights.source, map_location=torch.device("cpu"))
    model.load_state_dict(model_weights)
    pre_transformations = [get_instance(trf) for trf in pybio_model.spec.prediction.preprocess]
    post_transformations = [get_instance(trf) for trf in pybio_model.spec.prediction.postprocess]

    test_ipt = numpy.load(str(pybio_model.spec.test_input))
    assert test_ipt.shape == pybio_model.spec.inputs[0].shape
    test_out = numpy.load(str(pybio_model.spec.test_output))
    assert pybio_model.spec.outputs[0].shape.reference_input == pybio_model.spec.inputs[0].name
    assert all([s == 1 for s in pybio_model.spec.outputs[0].shape.scale])
    assert all([off == 0 for off in pybio_model.spec.outputs[0].shape.offset])
    assert test_out.shape == pybio_model.spec.inputs[0].shape

    test_roi = (slice(None), slice(None), slice(0, 32), slice(0, 32), slice(0, 32))  # to lower test mem consumption
    ipt = apply_transformations(pre_transformations, test_ipt[test_roi])
    assert isinstance(ipt, list)
    assert len(ipt) == 1
    ipt = ipt[0]
    out = model.forward(ipt)
    out = apply_transformations(post_transformations, out)
    assert isinstance(out, list)
    assert len(out) == 1
    out = out[0]
    # assert out.shape == pybio_model.spec.inputs[0].shape  # test_roi makes test invalid
    assert str(out.dtype).split(".")[-1] == pybio_model.spec.outputs[0].data_type
    assert numpy.allclose(test_out[test_roi], out, atol=0.1)  # test_roi requires atol >0.07876602
