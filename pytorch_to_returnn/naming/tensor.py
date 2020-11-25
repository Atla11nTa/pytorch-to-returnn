
from __future__ import annotations
from typing import Optional, List, Tuple, Dict
from weakref import ref
from returnn.tf.util.data import Data, DimensionTag
from . import _types
from . import namescope as _namescope
from . import module as _module
from . import call as _call


class TensorEntry:
  tensor: ref[_types.Tensor]
  returnn_data: Optional[Data] = None
  returnn_axis_to_torch_axis: Optional[Dict[int, int]] = None
  is_param: bool = False
  is_const: bool = False  # e.g. via from_numpy, empty, zeros, etc
  is_input: bool = False  # in TF1 terminology, would be a placeholder
  output_from_modules: List[_module.ModuleEntry]
  output_from_calls: List[_call.CallEntry]
  parent_owning_modules: List[Tuple[_module.ModuleEntry, str]]  # e.g. param or buffer
  creation_stack_call: Optional[_call.CallEntry]
  module_context_stack: List[_module.ModuleEntry]
  names: List[_namescope.RegisteredName]

  def __init__(self, tensor: ref[_types.Tensor],
               creation_stack_call: Optional[_call.CallEntry],
               module_context_stack: List[_module.ModuleEntry]):
    self.tensor = tensor
    self.creation_stack_call = creation_stack_call
    self.module_context_stack = module_context_stack
    self.output_from_modules = []
    self.output_from_calls = []
    self.parent_owning_modules = []
    self.names = []

  def __repr__(self):
    if self.returnn_data:
      returnn_data_repr = f"[{','.join(self.returnn_data.get_batch_axes_short_description())}]"
      if self.returnn_axis_to_torch_axis == {i: i for i in range(self.returnn_data.batch_ndim)}:
        mapping_repr = "id"
      else:
        mapping_repr = repr(self.returnn_axis_to_torch_axis).replace(" ", "")
      returnn_data_repr = f"{self.returnn_data.name!r} {returnn_data_repr} axes {mapping_repr}"
    else:
      returnn_data_repr = None
    tensor = self.tensor()
    tensor_repr = repr(tensor.shape).replace(" ", "") if tensor is not None else "?"
    name_repr = self.get_canonical_name(fallback='?')
    if name_repr != "?":
      name_repr = repr(name_repr)
    return (
      f"<{self.__class__.__name__ }"
      f" name:{name_repr}"
      f" tensor:{tensor_repr}"
      f" returnn_data:{returnn_data_repr}"
      f">")

  def get_canonical_parent_module(self,
                                  parent_namespace: Optional[_namescope.RegisteredName] = None
                                  ) -> Optional[_module.ModuleEntry]:
    if self.parent_owning_modules:
      return self.parent_owning_modules[0][0]
    if self.module_context_stack:
      mod = self.module_context_stack[-1]
      if parent_namespace and mod in parent_namespace.modules:
        pass
      else:
        return mod
    return None

  def get_canonical_name(self, *, fallback: Optional[str] = None) -> str:
    if self.parent_owning_modules:
      return self.parent_owning_modules[0][1]
    if fallback:
      return fallback
    raise NotImplementedError

  def get_returnn_axis_description(self, torch_axis: int) -> str:
    """
    :param torch_axis:
    :return: name such that
      self.returnn_axis_to_torch_axis[self.returnn_data.get_axis_from_description(name)] == torch_axis
    """
    assert self.returnn_data and self.returnn_axis_to_torch_axis is not None
    torch_axis_to_returnn_axis = {i: j for (j, i) in self.returnn_axis_to_torch_axis.items()}
    assert len(torch_axis_to_returnn_axis) == len(self.returnn_axis_to_torch_axis) == self.returnn_data.batch_ndim
    axis = torch_axis_to_returnn_axis[torch_axis]
    if axis == self.returnn_data.batch_dim_axis:
      return "B"
    if axis == self.returnn_data.time_dim_axis:
      return "T"
    if axis == self.returnn_data.feature_dim_axis:
      return "F"
    dim_tag = self.returnn_data.get_dim_tag(axis)
    assert dim_tag.kind == DimensionTag.Types.Spatial
    if dim_tag.dyn_size is not None:
      return f"stag:{dim_tag.description}"
    static_axes = self.returnn_data.get_static_axes()
    if axis in static_axes:
      return f"static:{static_axes.index(axis)}"
    spatial_axes = self.returnn_data.get_spatial_batch_axes()
    if axis in spatial_axes:
      return f"spatial:{spatial_axes.index(axis)}"
    raise Exception(f"Should not get here. Dim tag {dim_tag} for axis {axis} for data {self.returnn_data}")
