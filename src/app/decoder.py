from base64 import b64decode
from enum import IntEnum
from dataclasses import dataclass
import logging
from typing import List, Mapping, Tuple
import datetime

CURRENT_VERSION = 0x01


logger = logging.getLogger('cloudia-decoder')


class VarName(IntEnum):
    T = 0
    H = 1


@dataclass
class VarConf():
    nbits_v0: int
    signed: bool
    scale: float
    limits: Tuple[float, float]
    nbits_vi: int = -1


CONF: Mapping[VarName, VarConf] = {
    VarName.T: VarConf(nbits_v0=10,
                       signed=True,
                       scale=0.1,
                       limits=(-100.0, 100.0)),
    VarName.H: VarConf(nbits_v0=7,
                       signed=False,
                       scale=1.0,
                       limits=(0, 100))

}


class EncVar():
    def __init__(self, name: VarName):
        self.name = name
        conf = CONF[name]
        self.nbits_v0 = conf.nbits_v0
        self.nbits_vi = conf.nbits_v0
        self.signed = conf.signed


class DecVar():
    def __init__(self, name: VarName, raw: int, validate: bool = False):
        self.name = name
        conf = CONF[name]
        s = conf.scale
        lim = conf.limits

        self.raw = raw
        self.value = raw * s
        if validate:
            if self.value < lim[0] or self.value > lim[1]:
                logger.warning(
                    f"Variable {name} value ({self.value}) out of range {lim}")

    def __add__(self, other) -> 'DecVar':
        return DecVar(self.name, self.raw + other.raw, validate=True)


class Ports(IntEnum):
    SINGLE_MEAS = 70
    MULT_MEAS_OFFSET_0 = 80
    MULT_MEAS = 81
    MULT_MEAS_OFFSET_0_DIFFS = 90
    MULT_MEAS_DIFFS = 91


@dataclass
class Epoch():
    t: datetime.datetime
    v: List[DecVar]

    def to_tuple(self):
        return (self.t, {iv.name.value: iv.value for iv in self.v})


class BitDecompress():
    """
    Decompress bit-squeezed values from a buffer of bytes.
    This class implements an iterator that returns a set of variables (as defined by var_conf),
    one epoch at the time,  until the buffer is empty

    Arguments:
    - var_conf: List describing the properties of the variables in each epoch
    """

    def __init__(self,
                 buf: bytes,
                 var_conf: List[EncVar],
                 period: datetime.timedelta,
                 now: datetime.datetime = datetime.datetime.now(),
                 use_diffs: bool = False):

        self.buf: bytes = buf
        self.size = len(self.buf)
        self.byte_ptr = 0
        self.bit_ptr = 0
        self.conf = var_conf
        self.now = now
        self.period = period
        self.total_nbits_v0 = 0
        self.total_nbits_vi = 0
        self.use_diffs = use_diffs
        self.MASK: bytes = bytes(
            [0x01, 0x03, 0x07, 0x0F, 0x1F, 0x3F, 0x7F, 0xFF])

        for c in self.conf:
            self.total_nbits_v0 += c.nbits_v0
            self.total_nbits_vi += (c.nbits_vi if c.nbits_vi > 0 else 0)

        self.i = 0

    def _isEmpty(self) -> bool:
        remaining_nbits = (self.size - self.byte_ptr) * 8 - self.bit_ptr
        if self.i == 0:  # no element has been read
            return self.total_nbits_v0 > remaining_nbits
        else:
            return (self.total_nbits_vi < 1) or (self.total_nbits_vi > remaining_nbits)

    def __iter__(self):
        self.i = 0
        self.bit_ptr = 0
        self.byte_ptr = 0
        self.prev_dec_vars = [DecVar(i.name, 0) for i in self.conf]
        return self

    def __next__(self) -> Epoch:
        vars: List[DecVar] = []
        if self._isEmpty():
            raise StopIteration
        else:
            for c in self.conf:
                signed = c.signed or (self.use_diffs and self.i > 0)
                v = self._read(c.nbits_v0 if self.i ==
                               0 else c.nbits_vi, signed)
                dv = DecVar(c.name, v)
                vars.append(dv)
                t = self.now - self.i * self.period

        self.i += 1
        if self.use_diffs:
            # reconstruct full value based on the differences and the previous value
            vars = [vars[i] + self.prev_dec_vars[i] for i in range(len(vars))]
            self.prev_dec_vars = vars

        return Epoch(t=t, v=vars)

    def _read(self, nbits: int, signed: bool = False) -> int:
        """
        Extracts an int variable from the buffer given its width
        """
        sign = 0
        if signed:
            sign = (self.buf[self.byte_ptr] >> self.bit_ptr) & 0x1
            if self.bit_ptr < 7:
                self.bit_ptr += 1
            else:
                self.bit_ptr = 0
                self.byte_ptr += 1
        res = 0
        shift_by = 0
        while nbits:
            x = self.buf[self.byte_ptr]
            x >>= self.bit_ptr
            masked_bits = min(8 - self.bit_ptr, nbits)
            res |= (x & self.MASK[masked_bits - 1]) << shift_by
            shift_by += masked_bits
            nbits -= masked_bits
            if (8 - self.bit_ptr) > masked_bits:
                self.bit_ptr += masked_bits
            else:
                self.bit_ptr = 0
                self.byte_ptr += 1
        return -res if sign else res


class Decoder():
    offset: int = 0
    period: datetime.timedelta = datetime.timedelta(seconds=0)
    status: bytearray = bytearray([0, 0, 0, 0])
    var_conf: Mapping[VarName, EncVar] = {
        i: EncVar(i) for i in VarName
    }

    def __init__(self, port: int, payload_base64: str):
        self.payload = b64decode(payload_base64)
        self.port = port
        self.use_diffs: bool = False
        print(self.port, self.payload)

        self.status[0] = self.payload[0]
        self.status[1] = self.payload[1]

        self.version = ((self.status[0] << 2) | (
            (self.status[1] >> 6) & 0x3)) & 0x3FF

        if self.version != CURRENT_VERSION:
            raise NotImplementedError(
                f"Version: {self.version} not implemented")

        self.vbat = 2.5 + ((self.status[1] >> 2) & 0xF) / 10
        print(f"Vbatt: {self.vbat}")
        # TODO: remove T and / or H from var_conf if TEN or HEN are not set

        if self.port == Ports.SINGLE_MEAS:
            data = self.payload[2:]
        elif self.port == Ports.MULT_MEAS_OFFSET_0:
            self.status[2] = self.payload[2]
            data = self.payload[3:]
        elif self.port == Ports.MULT_MEAS:
            self.status[2] = self.payload[2]
            self.offset = self.payload[3]
            data = self.payload[4:]
        elif self.port == Ports.MULT_MEAS_OFFSET_0_DIFFS or self.port == Ports.MULT_MEAS_DIFFS:
            self.status[2] = self.payload[2]
            self.status[3] = self.payload[3]
            # number of bits used to encode the differences
            self.var_conf[VarName.T].nbits_vi = (self.status[3] >> 5) & 0x7
            self.var_conf[VarName.H].nbits_vi = (self.status[3] >> 2) & 0x7
            self.use_diffs = True

            data = self.payload[4:]
            if self.port == Ports.MULT_MEAS_DIFFS:
                self.offset = self.payload[4]
                data = self.payload[5:]
        else:
            raise NotImplementedError(f"Port {port} not implemented")

        period = self.status[2]
        if period != 0:
            if period & (1 << 7):  # value in secs
                self.period = datetime.timedelta(seconds=period & 0x7F)
            elif self.status[3] & (1 << 6):  # value in mins
                self.period = datetime.timedelta(minutes=period & 0x3F)
            else:
                self.period = datetime.timedelta(hours=period & 0x3F)
        else:
            self.period = 0

        print(f"PERIOD: {period} {self.period} {self.status[3]}")

        self.buffer = BitDecompress(data,
                                    list(self.var_conf.values()),
                                    self.period,
                                    use_diffs=self.use_diffs)

    def read_epochs(self) -> List[Tuple]:
        res: List[Tuple] = []

        for v in self.buffer:
            # print(v.to_tuple())
            res.append(v.to_tuple())

        return res


def decode(port: int, payload: str) -> List[Tuple[datetime.datetime, Mapping[str, float]]]:
    d = Decoder(port, payload)
    return d.read_epochs()
