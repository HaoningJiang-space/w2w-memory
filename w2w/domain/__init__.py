"""Immutable model contracts. Standard library only; no solvers or file I/O."""
from .execution import ExecutionGraph,ComputeTask,ResidentObject,ReadAccess,DataEdge,ControlEdge

__all__ = ['ExecutionGraph','ComputeTask','ResidentObject','ReadAccess','DataEdge','ControlEdge']
