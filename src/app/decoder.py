from base64 import b64decode
from enum import Enum
from typing import List, Literal, Mapping
import datetime
from pydantic import BaseModel, Field


class VarName(Enum):
    T = 'T'
    H = 'H'


class EncodedVar(BaseModel):
    name: VarName
    nbits_0: int  # number of bits of the first instance
    multiplier: float | int = 1
    signed: bool = False
    nbits_i: int = -1  # number of bits of successive instances


class Ports(Enum):
    SINGLE_MEAS = 80
    MULT_MEAS_OFFSET_0 = 81
    MULT_MEAS = 82
    MULT_MEAS_OFFSET_0_DIFFS = 90
    MULT_MEAS_DIFFS = 91


class DecodedVars(BaseModel):
    T: float = Field(le=100.0, ge=-100.0)
    H: int = Field(le=100, ge=0)


class Epoch(BaseModel):
    t: datetime.datetime
    vars: DecodedVars


class Buffer():
    def __init__(self, buf: bytes, var_conf: List[EncodedVar]):
        self.buf: bytes = buf
        self.size = len(self.buf)
        self.byte_ptr = 0
        self.bit_ptr = 0
        self.conf = var_conf
        self.MASK: bytes = bytes(
            [0x01, 0x03, 0x07, 0x0F, 0x1F, 0x3F, 0x7F, 0xFF])
        self.total_nbits_0 = 0
        self.total_nbits_i = 0

        for c in self.conf:
            self.total_nbits_0 += c.nbits_0
            self.total_nbits_i += (c.nbits_i if c.nbits_i > 0 else 0)

        self.i = 0

    def empty(self) -> bool:
        remaining_nbits = (self.size - self.byte_ptr) * 8 - self.bit_ptr
        if self.i == 0:  # no element has been read
            return self.total_nbits_0 > remaining_nbits
        else:
            return (self.total_nbits_i < 1) or (self.total_nbits_i > remaining_nbits)

    def __iter__(self):
        self.i = 0
        self.bit_ptr = 0
        self.byte_ptr = 0
        return self

    def __next__(self) -> List[float | int]:
        result: List[float | int] = []
        if self.empty():
            raise StopIteration
        else:
            if self.i == 0:
                # first reading
                for c in self.conf:
                    v = self.read(c.nbits_0, c.signed)
                    result.append(v * c.multiplier)
            else:
                for c in self.conf:
                    v = self.read(c.nbits_i, c.signed)
                    result.append(v * c.multiplier)

        self.i += 1
        return result

    def read(self, nbits: int, signed: bool = False):
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
    period: datetime.timedelta | None = None
    status: bytearray = bytearray([0, 0, 0])
    var_conf: Mapping[VarName, EncodedVar] = {
        VarName.T: EncodedVar(name=VarName.T, nbits_0=10, multiplier=1.0, signed=True),
        VarName.H: EncodedVar(name=VarName.H, nbits_0=7, multiplier=1, signed=False),
    }

    def __init__(self, port: int, payload_base64: str):
        self.payload = b64decode(payload_base64)
        self.port = Ports(port)
        print(self.port, self.payload)
        self.now = datetime.datetime.now()

        self.status[0] = self.payload[0]
        if self.port == Ports.SINGLE_MEAS:
            data = self.payload[1:]
        elif self.port == Ports.MULT_MEAS_OFFSET_0:
            self.status[1] = self.payload[1]
            data = self.payload[2:]
        elif self.port == Ports.MULT_MEAS:
            self.status[1] = self.payload[1]
            self.offset = self.payload[2]
            data = self.payload[3:]
        elif self.port == Ports.MULT_MEAS_OFFSET_0_DIFFS:
            self.status[1] = self.payload[1]
            self.status[2] = self.payload[2]
            # number of bits used to encode the differences
            self.var_conf[VarName.T].nbits_i = (self.status[2] >> 4) & 0xFF
            self.var_conf[VarName.H].nbits_i = self.status[2] & 0x0F
            data = self.payload[3:]
        elif self.port == Ports.MULT_MEAS_DIFFS:
            self.status[1] = self.payload[1]
            self.status[2] = self.payload[2]
            # number of bits used to encode the differences
            self.offset = self.payload[3]
            self.var_conf[VarName.T].nbits_i = (self.status[2] >> 4) & 0xFF
            self.var_conf[VarName.H].nbits_i = self.status[2] & 0x0F
            data = self.payload[4:]
        else:
            raise NotImplementedError(f"Port {port} not implemented")

        if self.status[2] & (1 << 7):  # value in secs
            self.period = datetime.timedelta(seconds=self.status[2] & 0x7F)
        elif self.status[2] & (1 << 6):  # value in mins
            self.period = datetime.timedelta(minutes=self.status[2] & 0x3F)
        else:
            self.period = datetime.timedelta(hours=self.status[2] & 0x3F)

        self.buffer = Buffer(data, list(self.var_conf.values()))

    def read_epochs(self) -> List[Epoch]:
        res: List[Epoch] = []

        for i in self.buffer:
            print(i)
