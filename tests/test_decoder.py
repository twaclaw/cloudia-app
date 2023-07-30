from app.decoder import decode, Ports, VarName, CONF, CURRENT_VERSION
from base64 import b64encode
from dataclasses import dataclass
from compress import Compress
import numpy as np
from typing import List, Mapping, Tuple


np.random.seed(0)


class Vector:
    def __init__(self, N: int, limits: Mapping[VarName, Tuple[int, int]]):
        self.N = N
        self.limits = limits
        self.data: Mapping[VarName, np.ndarray] = {}
        for k in self.limits:
            lo, up = self.limits[k]
            self.data[k] = np.random.randint(lo, up, N)


test_cases: List[Vector] = [
    Vector(N=1, limits={VarName.T: (200, 300), VarName.H: (50, 60)}),
    Vector(N=5, limits={VarName.T: (200, 210), VarName.H: (50, 60)}),
    Vector(N=10, limits={VarName.T: (200, 210), VarName.H: (40, 50)}),
    Vector(N=30, limits={VarName.T: (200, 300), VarName.H: (40, 99)}),
    Vector(N=100, limits={VarName.T: (200, 250), VarName.H: (60, 99)}),
]


@dataclass
class Var:
    data: np.ndarray
    nbits: int
    signed: bool


def create_buffer(vars: Mapping[VarName, Var],
                  vbatt: int = 38,
                  period: int = 15,
                  use_diffs: bool = True) -> Tuple[int, bytes]:

    # estimate differences
    N = len(vars[VarName.T].data)
    if N < 2:
        use_diffs = False
    else:
        diffs_nbits = {
            t: int(np.floor(np.log2(np.max(np.diff(vars[t].data))) + 1)) for t in VarName}

        diffs = {t: np.diff(vars[t].data) for t in VarName}

        if any([x > 8 for x in diffs_nbits.values()]) or N < 2:
            use_diffs = False
        SR4 = ((diffs_nbits[VarName.T] & 0x7) << 5) | (
            (diffs_nbits[VarName.H] & 0x7) << 2)

    vbatt -= 25
    SR1 = (CURRENT_VERSION >> 2) & 0xFF
    SR2 = ((CURRENT_VERSION & 0x3) << 6) | (((vbatt & 0xF) << 2) | 0x3)
    SR3 = period
    txdata = bytes([SR1, SR2])

    if N == 1:
        port = Ports.SINGLE_MEAS
    elif not use_diffs:
        txdata += bytes([SR3])
        port = Ports.MULT_MEAS_OFFSET_0
    else:
        txdata += bytes([SR3, SR4])
        port = Ports.MULT_MEAS_OFFSET_0_DIFFS

    B = Compress(255)
    # Add first value
    for i in range(1):
        for v in vars.values():
            data = v.data[i]
            nbits = v.nbits
            signed = v.signed
            if signed:
                B.add_with_sign(data, nbits)
            else:
                B.add(data, nbits)

    if use_diffs:
        for i in range(N - 1):
            for v in diffs:
                data = diffs[v][i]
                nbits = diffs_nbits[v]
                B.add_with_sign(data, nbits)

    else:
        for i in range(1, N):
            for v in vars.values():
                data = v.data[i]
                nbits = v.nbits
                signed = v.signed
                if signed:
                    B.add_with_sign(data, nbits)
                else:
                    B.add(data, nbits)

    txdata += B.array()
    return b64encode(txdata).decode(), port


class TestDecoder:
    def run_test(self, use_diffs: bool = True):
        for tv in test_cases:
            vars = {t: Var(tv.data[t], CONF[t].nbits_v0,
                           CONF[t].signed) for t in VarName}

            b, port = create_buffer(vars, use_diffs=use_diffs)
            d = decode(port, b)
            assert len(d) == tv.N
            data_read: Mapping[VarName, np.ndarray] = {
                v: np.array([]) for v in VarName}
            for i in d:
                dr = i[1]
                for v in VarName:
                    scale = 1 / CONF[v].scale
                    data_read[v] = np.append(data_read[v], int(dr[v]*scale))

            for v in VarName:
                assert np.allclose(data_read[v], tv.data[v])

    def test_edge_cases(self):
        b, port = "AHeUINLp7QI=", 90
        ref = {VarName.T: np.array([233., 232., 233., 232., 233., 233., 233., 233.]),
               VarName.H: np.array([61., 61., 61., 61., 61., 61., 61., 61.])}
        d = decode(port, b)
        data_read: Mapping[VarName, np.ndarray] = {
            v: np.array([]) for v in VarName}
        for i in d:
            dr = i[1]
            for v in VarName:
                scale = 1 / CONF[v].scale
                data_read[v] = np.append(data_read[v], int(dr[v] * scale))

        for v in VarName:
            assert np.allclose(data_read[v], ref[v])

    def test_all(self):
        # self.run_test(use_diffs=False)
        self.run_test(use_diffs=True)
