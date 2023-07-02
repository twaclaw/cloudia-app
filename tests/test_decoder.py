from app.decoder import decode, Ports, VarName, CONF, CURRENT_VERSION
from base64 import b64encode
from dataclasses import dataclass
from compress import Compress
import numpy as np
from typing import List, Mapping, Tuple

N = 50
T_range = (200, 250)
H_range = (40, 50)

DATA: Mapping[VarName, np.ndarray] = {VarName.T: np.random.randint(T_range[0], T_range[1], N),
                                      VarName.H: np.random.randint(H_range[0], H_range[1], N)}


@dataclass
class Var:
    data: np.ndarray
    nbits: int
    signed: bool


def create_buffer(vars: Mapping[VarName, Var],
                  N: int,
                  vbatt: int = 38,
                  period: int = 15,
                  use_diffs: bool = True) -> Tuple[int, bytes]:

    # estimate differences
    diffs_nbits = {
        t: int(np.floor(np.log2(np.max(np.diff(vars[t].data))) + 1)) for t in VarName}

    diffs = {t: np.diff(vars[t].data) for t in VarName}

    if any([x > 8 for x in diffs_nbits.values()]) or N < 2:
        use_diffs = False

    vbatt -= 25
    SR1 = (CURRENT_VERSION >> 2) & 0xFF
    SR2 = ((CURRENT_VERSION & 0x3) << 6) | (((vbatt & 0xF) << 2) | 0x3)
    SR3 = period
    SR4 = ((diffs_nbits[VarName.T] & 0x7) << 5) | (
        (diffs_nbits[VarName.H] & 0x7) << 2)

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


vars = {t: Var(DATA[t], CONF[t].nbits_v0, CONF[t].signed) for t in VarName}

b, port = create_buffer(vars, 50, use_diffs=True)

d = decode(port, b)
