import numpy as np
from typing import Dict, List


MASK = [0x01, 0x03, 0x07, 0x0F, 0x1F, 0x3F, 0x7F, 0xFF]


class Compress():
    def __init__(self, N: int):
        """
        Implements a compression buffer of size N bytes.
        """
        self.buf = np.zeros(N, dtype=np.uint8)
        self.N = N
        self.byte_ptr = 0
        self.bit_ptr = 0

    def reset(self):
        self.byte_ptr = 0
        self.bit_ptr = 0

    def __str__(self):
        pl = [f"{i:02x}" for i in self.buf]
        return f"byte-ptr:{self.byte_ptr}, bit-ptr: {self.bit_ptr}, buff:" + "".join(pl[:self.byte_ptr + 1])

    def add(self, x, nbits):
        """
        Adds value x of size nbits to the buffer.
        """
        while nbits:
            shift_by = min(nbits, 8 - self.bit_ptr)
            assert shift_by > 0
            y = np.uint8(x & MASK[shift_by - 1])
            y <<= self.bit_ptr
            self.buf[self.byte_ptr] |= y
            nbits -= shift_by
            x >>= shift_by

            if (8 - self.bit_ptr) > shift_by:
                self.bit_ptr += shift_by
            else:
                self.bit_ptr = 0
                self.byte_ptr += 1

    def add_with_sign(self, x, nbits):
        if x < 0:
            self.add(1, 1)
        else:
            self.add(0, 1)
        self.add(abs(x), nbits)

    def array(self) -> bytes:
        up: int = self.byte_ptr
        up += 1 if self.bit_ptr > 0 else 0
        return bytes(self.buf[:up])
