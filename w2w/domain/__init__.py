"""Immutable model contracts. Standard library only; no solvers or file I/O."""
from .design import Geometry, Exposure, StaticLayout, MemoryFabricDesign
from .endpoint import EndpointSpec, NativeProfile, EndpointEnvelope, LinearLimit

__all__ = ['Geometry', 'Exposure', 'StaticLayout', 'MemoryFabricDesign',
           'EndpointSpec', 'NativeProfile', 'EndpointEnvelope', 'LinearLimit']
