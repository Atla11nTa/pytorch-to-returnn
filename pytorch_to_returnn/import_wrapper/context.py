
from typing import Set, Iterable, Dict, Optional, Callable, TypeVar, Type


class WrapCtx:
  def __init__(self,
               wrapped_mod_prefix: str,
               wrap_mods_direct: Set[str], wrap_mods_indirect: Set[str] = None,
               keep_as_is_types: Iterable[type] = (),
               explicit_wrapped_types: Dict[type, "ExplicitWrappedType"] = None):
    """
    :param wrapped_mod_prefix: e.g. "pytorch_to_returnn._wrapped_mods."
    :param wrap_mods_direct: e.g. {"torch.nn.modules"}
      These modules will be imported using the direct AST transformation,
      and result in :class:`WrappedSourceModule`.
    :param wrap_mods_indirect: e.g. {"torch", "torch.nn.modules.module"}
      These modules will be wrapped using :class:`WrappedIndirectModule`,
      which wraps the originally unmodified imported module.
      There can be overlaps between wrap_mods_direct and wrap_mods_indirect.
      The topmost entry will decide whether it is direct or indirect.
    :param keep_as_is_types: e.g. {torch.device, torch.dtype, torch.Size}
    :param explicit_wrapped_types: e.g. {torch.Tensor: ExplicitWrappedType(WrappedTorchTensor...)}
    """
    assert wrapped_mod_prefix.endswith(".")
    self.wrapped_mod_prefix = wrapped_mod_prefix
    self.wrap_mods_direct = wrap_mods_direct
    if wrap_mods_indirect is None:
      wrap_mods_indirect = set()  # type: Set[str]
    self.wrap_mods_indirect = wrap_mods_indirect
    self.keep_as_is_types = tuple(keep_as_is_types)
    if explicit_wrapped_types is None:
      explicit_wrapped_types = {}  # type: Dict[type, "ExplicitWrappedType"]
    self.explicit_wrapped_types = explicit_wrapped_types

  def __repr__(self):
    return "<%s %r>" % (self.__class__.__name__, self.wrapped_mod_prefix[:-1])

  def should_wrap_mod(self, mod_name: str) -> bool:
    """
    :param mod_name: e.g. "torch"
    """
    mod_name = mod_name.split(".")
    for i in range(1, len(mod_name) + 1):
      if ".".join(mod_name[:i]) in self.wrap_mods_direct:
        return True
      if ".".join(mod_name[:i]) in self.wrap_mods_indirect:
        return True
    return False


class ExplicitWrappedType:
  _OrigType = TypeVar("_OrigType")
  _NewType = TypeVar("_NewType")
  _WrapFuncType = Callable[[_OrigType], _NewType]

  def __init__(self, orig_type: Type[_OrigType], new_type: Type[_NewType], wrap: Optional[_WrapFuncType]):
    self.orig_type = orig_type
    self.new_type = new_type
    self._wrap = wrap

  def wrap(self, obj: _OrigType, *, name: str, ctx: WrapCtx) -> _NewType:
    if self._wrap:
      return self._wrap(obj)
    return self.new_type(orig_obj=obj, name=name, ctx=ctx)


def make_torch_default_ctx(wrapped_mod_prefix: str) -> WrapCtx:
  import torch
  from .torch_wrappers import WrappedTorchTensor, WrappedTorchParameter, WrappedModuleBase

  _KeepAsIsTypes = (
    torch.device,
    torch.Size,
    torch.dtype,
  )

  def _wrap_tensor(obj):
    assert isinstance(obj, torch.Tensor)
    obj = obj.as_subclass(WrappedTorchTensor)
    return obj

  # noinspection PyUnusedLocal
  def _raise_not_implemented(*args):
    raise NotImplementedError

  _TypeMap = {
    torch.Tensor: ExplicitWrappedType(torch.Tensor, WrappedTorchTensor, wrap=_wrap_tensor),
    torch.nn.Parameter: ExplicitWrappedType(torch.nn.Parameter, WrappedTorchParameter, wrap=_raise_not_implemented),
    torch.nn.Module: ExplicitWrappedType(torch.nn.Module, WrappedModuleBase, wrap=_raise_not_implemented),
  }

  return WrapCtx(
    wrapped_mod_prefix=wrapped_mod_prefix,
    wrap_mods_direct=_TorchExplicitDirectModList,
    wrap_mods_indirect=_TorchExplicitIndirectModList,
    keep_as_is_types=_KeepAsIsTypes,
    explicit_wrapped_types=_TypeMap)


_TorchExplicitIndirectModList = {
  # Leave "torch" in to not do any magic on the original Torch modules.
  # Note that the main torch module cannot be transformed
  # because of some side-effects triggered by native Torch code,
  # which we cannot catch automatically.
  # More specifically, in torch/__init__.py, there is the call _C._initExtension,
  # which (un-intuitively) does all sorts of initialization,
  # including torch::utils::initializeDtypes,
  # which itself has the side-effect of adding dtypes (e.g. `float32`)
  # to the `torch` module (-> `torch.float32`).
  # And the name `"torch"` is hardcoded there,
  # i.e. it will not used our wrapped module,
  # thus we will never have `float32` registered,
  # and that leads to exceptions.
  # This is likely not the only problem.
  "torch",
}
if "torch" in _TorchExplicitIndirectModList:
  _TorchExplicitIndirectModList.update({
    # If we would transform `torch` directly, the following should be explicitly excluded.
    "torch.tensor", "torch.distributed",
    "torch._C",
    # Avoid to have the `Module` class twice.
    "torch.nn.modules.module",
  })

_TorchExplicitDirectModList = {
  # Note: When we don't wrap all of `torch` (i.e. `"torch"` is in _ExplicitIndirectModList),
  # this will partially be WrappedIndirectModule and WrappedSourceModule.
  # This is not a problem in principle, but there can be subtle problems.
  # Also the import order can be important.
  # E.g. "torch.nn.modules" should be imported before "torch.nn.functional".
  # This might need extra explicit handling, depending what we have here in this list.
  "torch.nn.modules",
  # "torch.nn.functional",  # -- not needed, also causes other problems
}
