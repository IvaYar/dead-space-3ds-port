"""Inspect the straight-line shaders used by this experiment, not a general ISA validator."""
import struct


def words(blob):
    assert len(blob) % 4 == 0
    return struct.unpack('<' + 'I' * (len(blob) // 4), blob)


def shader(blob):
    w = words(blob)
    assert blob[:4] == b'DVLB' and w[1] == 1
    base = 2 + w[1]
    assert blob[base * 4:base * 4 + 4] == b'DVLP'
    code = w[base + w[base + 2] // 4:base + w[base + 2] // 4 + w[base + 3]]
    descriptors = [w[base + w[base + 4] // 4 + 2 * i] for i in range(w[base + 5])]
    dvle = w[2] // 4
    output_offset = w[2] + w[dvle + 10]
    declared = {}
    for i in range(w[dvle + 11]):
        kind, register, mask = struct.unpack_from('<HHB', blob, output_offset + 8 * i)
        declared[register] = declared.get(register, 0) | mask
    counts = {r: [0] * 4 for r in declared}
    instructions = []
    for pc in range(w[dvle + 2], w[dvle + 3]):
        instruction = code[pc]
        opcode = instruction >> 26
        if opcode == 0x22:  # END; neither shader has flow control.
            assert pc == w[dvle + 3] - 1
            break
        assert opcode in (0x02, 0x08, 0x13), f'Unsupported opcode {opcode:x}'  # DP4, MUL, MOV
        dest = (instruction >> 21) & 31
        descriptor = instruction & 127
        mask = descriptors[descriptor] & 15
        instructions.append(dict(pc=pc, opcode=opcode, dest=dest, mask=mask,
                                 descriptor=descriptor, word=f'{instruction:08x}'))
        if dest in counts:
            for component in range(4):
                counts[dest][component] += bool(mask & (8 >> component))
    else:
        raise AssertionError('No END')
    outputs = []
    for register, declared_mask in declared.items():
        written = sum((8 >> i) for i, n in enumerate(counts[register]) if n)
        outputs.append(dict(register=register, declared_mask=declared_mask, written_mask=written,
                            writes_xyzw=counts[register],
                            missing=''.join(c for i, c in enumerate('xyzw')
                                            if declared_mask & (8 >> i) and not counts[register][i])))
    return dict(code_words=list(code), descriptors=descriptors, instructions=instructions,
                outputs=outputs, all_declared_components_once=all(
                    n == 1 for r, mask in declared.items() for i, n in enumerate(counts[r])
                    if mask & (8 >> i)))


def command_list(blob):
    """Decode packet bounds and byte masks; preserve order and FIFO writes."""
    assert len(blob) % 16 == 0
    w = words(blob)
    cursor, packets, writes, state = 0, [], [], {}
    while cursor < len(w):
        assert cursor + 2 <= len(w)
        header = w[cursor + 1]
        extra = (header >> 20) & 0x7ff
        assert cursor + 2 + extra <= len(w)
        values = [w[cursor], *w[cursor + 2:cursor + 2 + extra]]
        reg, mask = header & 65535, (header >> 16) & 15
        lane_mask = sum(255 << (8 * i) for i in range(4) if mask & (1 << i))
        for i, value in enumerate(values):
            address = reg + (i if header >> 31 else 0)
            state[address] = (state.get(address, 0) & ~lane_mask) | (value & lane_mask)
            writes.append(dict(byte_offset=4 * (cursor if i == 0 else cursor + i + 1),
                               reg=address, mask=mask, value=value))
        packets.append(dict(word=cursor, register=reg, mask=mask, values=values))
        cursor += extra + 2
        cursor += cursor & 1
    assert cursor == len(w)
    return dict(packets=packets, writes=writes, state=state)
