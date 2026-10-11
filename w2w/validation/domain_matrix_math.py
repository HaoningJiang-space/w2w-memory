"""Small independent E4M3FN/BF16 oracle for row ownership, not native compute."""
import math,struct


def f32(x):return struct.unpack('<f',struct.pack('<f',x))[0]


def bf16(x):
    bits=struct.unpack('<I',struct.pack('<f',x))[0]
    if bits&0x7f800000==0x7f800000:raise ValueError('Finite oracle inputs required')
    bits=(bits+0x7fff+((bits>>16)&1))&0xffff0000
    return struct.unpack('<f',struct.pack('<I',bits))[0]


def e4m3fn(byte):
    if type(byte) is not int or not 0<=byte<256:raise ValueError('An FP8 encoding is one byte')
    sign=-1 if byte&128 else 1;exponent=(byte>>3)&15;mantissa=byte&7
    if exponent==15 and mantissa==7:raise ValueError('No NaN in finite equivalence oracle')
    return sign*(mantissa*2**-9 if exponent==0 else (1+mantissa/8)*2**(exponent-7))


def row_projection(encoded, scales, x, first, last):
    rows=len(encoded);cols=len(x)
    if rows%128 or cols%128 or len(scales)!=(rows//128)*(cols//128):
        raise ValueError('Preserve complete original 128x128 quantization groups')
    if not 0<=first<=last<=rows or any(len(row)!=cols for row in encoded):raise ValueError('Invalid complete output rows')
    out=[]
    for row in range(first,last):
        acc=0.0
        for col in range(cols):
            scale=scales[(row//128)*(cols//128)+col//128]
            product=f32(f32(e4m3fn(encoded[row][col])*scale)*x[col])
            acc=f32(acc+product)
        out.append(acc)
    return out


def validate_row_partition(gate,up,down,gate_scales,up_scales,down_scales,x,parts=8):
    h=len(x);width=len(gate)
    if h%parts or width%parts or len(up)!=width or len(down)!=h:raise ValueError('Integral output ownership required')
    x=[bf16(v) for v in x]
    def projections(parts):
        def tiled(w,s,v):
            n=len(w);return [a for i in range(parts) for a in row_projection(w,s,v,i*n//parts,(i+1)*n//parts)]
        g,u=tiled(gate,gate_scales,x),tiled(up,up_scales,x)
        activation=[bf16(f32(f32(a/(1+math.exp(-a)))*b)) for a,b in zip(g,u)]
        return g,u,activation,tiled(down,down_scales,activation)
    reference=projections(1);candidate=projections(parts)
    if reference!=candidate:raise ValueError('Output ownership changed original scale, dot or BF16 ordering')
    return dict(passed=True,parts=parts,hidden=h,block_width=width,
        output_ownership_equivalent=True,unchanged_hidden_and_down_reduction_order=True,
        contract='Finite synthetic E4M3FN, original FP32 scale groups, ordered float32 dot and BF16 round-to-nearest-even H. '
            'Row splitting/concatenation only. Not a numerical WSE/SeDRAM or native SiLU calibration; no fragment-order reassociation.')
