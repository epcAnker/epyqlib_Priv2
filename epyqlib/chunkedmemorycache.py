import attr
import bisect
import collections


class ChunkExistsError(Exception):
    pass


class ByteLengthError(Exception):
    pass


@attr.s
class Cache:
    _chunks = attr.ib(init=False, default=attr.Factory(list))
    _subscribers = attr.ib(init=False, default=attr.Factory(dict))
    _bits_per_byte = attr.ib(default=8)

    def add(self, chunk):
        if chunk in self._subscribers.keys():
            # TODO: just return because it's already added?
            raise ChunkExistsError()

        if any(chunk == c for c in self._chunks):
            # TODO: who cares if there are duplicates?
            raise ChunkExistsError()

        bisect.insort_left(self._chunks, chunk)
        self._subscribers[chunk] = set()

    def subscribe(self, subscriber, chunk):
        self._subscribers[chunk].add(subscriber)

    def unsubscribe(self, subscriber, chunk):
        self._subscribers[chunk].discard(subscriber)

    def update(self, update_chunk):
        for chunk in self._chunks:
            if chunk.update(update_chunk):
                for subscriber in self._subscribers.get(chunk, ()):
                    subscriber(chunk._bytes)

    def chunk_from_variable(self, variable):
        data = bytearray([0] * variable.type.bytes * (self._bits_per_byte // 8))
        return Chunk(address=variable.address,
                     bytes=data,
                     bits_per_byte=self._bits_per_byte)

    def new_chunk(self, address, bytes):
        return Chunk(address=address,
                     bytes=bytes,
                     bits_per_byte=self._bits_per_byte)


@attr.s(hash=False)
class Chunk:
    _address = attr.ib()
    _bytes = attr.ib(convert=lambda value: bytearray(value))
    _bits_per_byte = attr.ib(default=8)

    def __len__(self):
        return len(self._bytes)

    def __hash__(self):
        return hash((self._address, len(self)))

    def bounds(self):
        return (self._address,
                self._address + len(self) // (self._bits_per_byte // 8))

    def __lt__(self, other):
        if not isinstance(other, self.__class__):
            return NotImplemented

        return self._address < other._address or (
            self._address == other._address and len(self) < len(other)
        ) 

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return NotImplemented

        return self._address == other._address and len(self) == len(other)

    def set_bytes(self, new_bytes):
        if len(new_bytes) != len(self):
            raise ByteLengthError("A chunk's byte array may not change length")

        self._bytes = bytearray(new_bytes)

    def update(self, chunk):
        my_bounds = self.bounds()
        chunk_bounds = chunk.bounds()

        start = max(my_bounds[0], chunk_bounds[0])
        end = min(my_bounds[1], chunk_bounds[1])

        _length = end - start

        if _length >= 1:
            slice_start = (start - self._address) * (self._bits_per_byte // 8)
            slice_end = (slice_start + _length) * (self._bits_per_byte // 8)
            self_slice = slice(slice_start, slice_end)

            slice_start = (start - chunk._address) * (self._bits_per_byte // 8)
            slice_end = (slice_start + _length) * (self._bits_per_byte // 8)
            chunk_slice = slice(slice_start, slice_end)

            self._bytes[self_slice] = chunk._bytes[chunk_slice]

            print('chunk updated: {}'.format(self))
            return True
        
        return False


def testit(filename):
    import epyqlib.cmemoryparser
    import functools
    import random

    names, variables, bits_per_byte = epyqlib.cmemoryparser.process_file(filename)

    cache = Cache(bits_per_byte=bits_per_byte)

    for variable in variables:
        chunk = cache.chunk_from_variable(variable)
        cache.add(chunk)
        partial = functools.partial(testit_updated,
                                    variable)
        cache.subscribe(subscriber=partial, chunk=chunk)
        print('added {}: {}'.format(variable.name, chunk))

    chunk = cache.chunk_from_variable(names['Vholdoff'])
    new_bytes = [random.randint(0, 255) for _ in range(len(chunk))]
    chunk.set_bytes(new_bytes)
    print('sending update: {}'.format(chunk))
    cache.update(chunk)

    testStruct12 = names['testStruct12']
    TestStruct12 = epyqlib.cmemoryparser.base_type(testStruct12)
    # TODO: but this is bit packed so not all those bytes!  but maybe it's
    #       ok and bitfields must all be updated at once?  hmm..
    chunk = cache.new_chunk(
        address=testStruct12.address,
        # bytes=[255] * TestStruct12.members[0].bytes * (bits_per_byte // 8)
        bytes=[random.randint(0, 255) for _ in
               range(TestStruct12.members['m9'].bytes * (bits_per_byte // 8))]
    )
    print('sending update: {}'.format(chunk))
    cache.update(chunk)


def testit_updated(variable, bytes):
    print('{} was updated: {} -> {}'.format(variable.name, bytes, variable.unpack(bytes)))


if __name__ == '__main__':
    import sys

    sys.exit(testit(sys.argv[1]))