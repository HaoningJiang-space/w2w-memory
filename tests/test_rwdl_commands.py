"""Causal command audit fixtures; malformed traces cannot pass on byte counts."""
import unittest
from w2w.architecture.memory_wafer import NativePolicy
from dataclasses import asdict
from w2w.validation.rwdl_commands import audit_channel


def row(at,cmd,r=0,col=0):
    return dict(clock=str(at),command=cmd,Channel='0',Rank='0',Bank='0',Row=str(r),Column=str(col))


class CommandAudit(unittest.TestCase):
    def test_row_change_and_refresh_constraints(self):
        rows=[row(1,'ACT'),row(5,'RD'),row(6,'RD',col=1),row(10,'PREpb'),
            row(14,'ACT',1),row(18,'RD',1),row(23,'PREab'),row(27,'REFab'),row(199,'ACT',2),row(203,'RD',2)]
        atoms,record=audit_channel(rows,asdict(NativePolicy()),0,64*1024**2)
        self.assertEqual(sum(atoms.values()),4)
        self.assertEqual(record['commands']['REFab'],1)
        self.assertEqual(set(atoms),{(0,0),(0,1),(0,64),(0,128)})
        rows[-2]=row(198,'ACT',2)
        with self.assertRaises(ValueError):audit_channel(rows,asdict(NativePolicy()),0,64*1024**2)

    def test_wrong_operand_and_early_read(self):
        for rows in ([row(1,'ACT'),row(4,'RD')],[row(1,'ACT'),row(5,'RD',1)],
                     [row(1,'ACT'),row(5,'WR')],[row(1,'ACT'),row(5,'RD'),row(5,'RD',col=1)]):
            with self.assertRaises(ValueError):audit_channel(rows,asdict(NativePolicy()),0,64*1024**2)


if __name__=='__main__':unittest.main()
