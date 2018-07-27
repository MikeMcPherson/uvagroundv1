'''
   Chaskey reference Python implementation, (c) 2014 Bart Mennink

   To the extent possible under law, the author has dedicated all copyright and
   related and neighboring rights to this software to the public domain worldwide.
   This software is distributed without any warranty. See also CC0 Public Domain
   Dedication: <http://creativecommons.org/publicdomain/zero/1.0>.

   Implementation inspired by Marek Majkowski's SipHash implementation, to which
   MIT's open source license applies. See <http://opensource.org/licenses/MIT>.
   
   NOTE 1: This implementation assumes a little-endian architecture.
   NOTE 2: This implementation follows the 'hashlib' and 'hmac' APIs,
           with the difference that user-input tag length is allowed.
'''
'''
   in: key "k" of size 32 hex
       optional tag length "tlen", at most 16
       optional message chunk "msg", arbitrary length
   out: digest of size tlen char (of digest())
        digest of size 2*tlen hex (of hexdigest())
   >>> instance = chaskey(b'chaskey is a mac',9,b'message part 1')
   >>> instance.update(b'message part 2')
   >>> instance2 = instance.copy()
   >>> instance.digest()
   b'f\xcc.\xca\xa6V\xf1\x19V'
   >>> len(instance.digest())
   9
   >>> instance2.update(b'message part 3')
   >>> instance2.hexdigest()
   b'0b27524b40da5a07d0'
   >>> len(instance2.hexdigest())
   18
''' 
import struct
import binascii
import hexdump

debugk       = 0
debugm       = 0
debugst      = 0
debugstfinal = 0

_block = struct.Struct('<L')
_fourblock = struct.Struct('<LLLL')
_zeroes = b'\x00'*16
_C = ( b'\x00\x00\x00\x00', b'\x87\x00\x00\x00' )
_mask = 0xffffffff

def _doublekey(k):
    '''in: k
       out: 2k'''
    k0, k1, k2, k3 = k
    carry, = _block.unpack(_C[k3 >> 31])
    l0 = ( (k0 & 0x7fffffff) << 1) ^ carry
    l1 = ( (k1 & 0x7fffffff) << 1) | (k0 >> 31)
    l2 = ( (k2 & 0x7fffffff) << 1) | (k1 >> 31)
    l3 = ( (k3 & 0x7fffffff) << 1) | (k2 >> 31)
    return (l0,l1,l2,l3)

def _keygen(k):
    '''in: k packed
       out: k,2k,4k unpacked'''
    key = _fourblock.unpack(k)
    key1 = _doublekey(key)
    key2 = _doublekey(key1)
    if debugk:
        print("  key:       %08x %08x %08x %08x" % key)
        print("2 key:       %08x %08x %08x %08x" % key1)
        print("4 key:       %08x %08x %08x %08x" % key2)
    return (key,key1,key2)

def _rotl(a,i):
    '''in: state chunk a
       out: a left-rotated by i bits'''
    return ( ((a << i) & _mask) | (a >> (32-i)) )

def _chaskeyround(st):
    '''in:  state st
       out: updated state after round'''
    st0, st1, st2, st3 = st
    st0 = ( st0 + st1 ) & _mask
    st1 = _rotl(st1,5) ^ st0
    st2 = ( st2 + st3 ) & _mask
    st3 = _rotl(st3,8) ^ st2

    st0 = ( _rotl(st0,16) + st3 ) & _mask
    st2 = ( st1 + st2 ) & _mask
    st1 = _rotl(st1,7) ^ st2
    st3 = _rotl(st3,13) ^ st0

    st2 = _rotl(st2,16)
    return (st0,st1,st2,st3)

def _chaskeypermute(st):
    '''in:  state st
       out: updated state after permutation'''
    st = _chaskeyround(st)
    if debugst:   print("st round1:   %08x %08x %08x %08x" % st)
    st = _chaskeyround(st)
    if debugst:   print("st round2:   %08x %08x %08x %08x" % st)
    st = _chaskeyround(st)
    if debugst:   print("st round3:   %08x %08x %08x %08x" % st)
    st = _chaskeyround(st)
    if debugst:   print("st round4:   %08x %08x %08x %08x" % st)
    st = _chaskeyround(st)
    if debugst:   print("st round5:   %08x %08x %08x %08x" % st)
    st = _chaskeyround(st)
    if debugst:   print("st round6:   %08x %08x %08x %08x" % st)
    st = _chaskeyround(st)
    if debugst:   print("st round7:   %08x %08x %08x %08x" % st)
    st = _chaskeyround(st)
    if debugst:   print("st round8:   %08x %08x %08x %08x" % st)
    return st

class chaskey:
    def __init__(self, k, tlen=8, msg=b''):
        print('Chaskey key')
        hexdump.hexdump(key)
        print('Chaskey msg')
        hexdump.hexdump(msg)
        assert(tlen <= 16)
        self.key, self.key1, self.key2 = _keygen(k) #subkeys can be precomputed for speedup
        self.st = self.key
        self.tlen = tlen
        self.msg = b''
        self.update(msg)

    def update(self,msg):
        msg = self.msg + msg
        blen = ((len(msg)-1)//16)*16
        # blen = number of chars that can be processed
        # note: if len(msg)%16==0, a full block should remain for finalization
        st = self.st
        if debugm:   print("message length %02d" % len(msg))
        if debugst:   print("st:          %08x %08x %08x %08x" % st)

        for i in range(0,blen,16):
            m = _fourblock.unpack_from(msg, i)
            if debugm:   print("compress m:  %08x %08x %08x %08x" % m)
            st = st[0]^m[0], st[1]^m[1], st[2]^m[2], st[3]^m[3]
            if debugst:   print("st:          %08x %08x %08x %08x" % st)
            st = _chaskeypermute(st)

        self.st = st
        self.msg = msg[blen:]
        return self

    def hash(self):
        st = self.st
        mlen = len(self.msg)
        assert(mlen <= 16)

        if mlen == 16:
            k = self.key1
            m = _fourblock.unpack_from(self.msg)
        else:
            k = self.key2
            m = _fourblock.unpack_from(self.msg+b'\x01'+_zeroes)

        if debugm:   print("last m:      %08x %08x %08x %08x" % m)
        st = st[0]^k[0]^m[0], st[1]^k[1]^m[1], st[2]^k[2]^m[2], st[3]^k[3]^m[3]
        if debugst:   print("st:          %08x %08x %08x %08x" % st)
        st = _chaskeypermute(st)
        st = st[0]^k[0], st[1]^k[1], st[2]^k[2], st[3]^k[3]
        if debugstfinal:   print("st final:    %08x %08x %08x %08x" % st)

        self.st = st
        return self

    def digest(self):
        self.hash()
        concat = _fourblock.pack(self.st[3],self.st[2],self.st[1],self.st[0])
        return concat[16-self.tlen:16]

    def hexdigest(self):
        self.hash()
        concat = _fourblock.pack(self.st[3],self.st[2],self.st[1],self.st[0])
        return binascii.hexlify(concat)[32-2*self.tlen:32]

    def copy(self):
        n = chaskey(_zeroes)
        n.st, n.key, n.key1, n.key2, n.tlen, n.msg = self.st, self.key, self.key1, self.key2, self.tlen, self.msg
        return n
'''
if __name__ == "__main__":
    vectors = [binascii.hexlify(_fourblock.pack(v[3], v[2], v[1], v[0])) for v in [
        ( 0x792E8FE5, 0x75CE87AA, 0x2D1450B5, 0x1191970B ),
        ( 0x13A9307B, 0x50E62C89, 0x4577BD88, 0xC0BBDC18 ),
        ( 0x55DF8922, 0x2C7FF577, 0x73809EF4, 0x4E5084C0 ),
        ( 0x1BDBB264, 0xA07680D8, 0x8E5B2AB8, 0x20660413 ),
        ( 0x30B2D171, 0xE38532FB, 0x16707C16, 0x73ED45F0 ),
        ( 0xBC983D0C, 0x31B14064, 0x234CD7A2, 0x0C92BBF9 ),
        ( 0x0DD0688A, 0xE131756C, 0x94C5E6DE, 0x84942131 ),
        ( 0x7F670454, 0xF25B03E0, 0x19D68362, 0x9F4D24D8 ),
        ( 0x09330F69, 0x62B5DCE0, 0xA4FBA462, 0xF20D3C12 ),
        ( 0x89B3B1BE, 0x95B97392, 0xF8444ABF, 0x755DADFE ),
        ( 0xAC5B9DAE, 0x6CF8C0AC, 0x56E7B945, 0xD7ECF8F0 ),
        ( 0xD5B0DBEC, 0xC1692530, 0xD13B368A, 0xC0AE6A59 ),
        ( 0xFC2C3391, 0x285C8CD5, 0x456508EE, 0xC789E206 ),
        ( 0x29496F33, 0xAC62D558, 0xE0BAD605, 0xC5A538C6 ),
        ( 0xBF668497, 0x275217A1, 0x40C17AD4, 0x2ED877C0 ),
        ( 0x51B94DA4, 0xEFCC4DE8, 0x192412EA, 0xBBC170DD ),
        ( 0x79271CA9, 0xD66A1C71, 0x81CA474E, 0x49831CAD ),
        ( 0x048DA968, 0x4E25D096, 0x2D6CF897, 0xBC3959CA ),
        ( 0x0C45D380, 0x2FD09996, 0x31F42F3B, 0x8F7FD0BF ),
        ( 0xD8153472, 0x10C37B1E, 0xEEBDD61D, 0x7E3DB1EE ),
        ( 0xFA4CA543, 0x0D75D71E, 0xAF61E0CC, 0x0D650C45 ),
        ( 0x808B1BCA, 0x7E034DE0, 0x6C8B597F, 0x3FACA725 ),
        ( 0xC7AFA441, 0x95A4EFED, 0xC9A9664E, 0xA2309431 ),
        ( 0x36200641, 0x2F8C1F4A, 0x27F6A5DE, 0x469D29F9 ),
        ( 0x37BA1E35, 0x43451A62, 0xE6865591, 0x19AF78EE ),
        ( 0x86B4F697, 0x93A4F64F, 0xCBCBD086, 0xB476BB28 ),
        ( 0xBE7D2AFA, 0xAC513DE7, 0xFC599337, 0x5EA03E3A ),
        ( 0xC56D7F54, 0x3E286A58, 0x79675A22, 0x099C7599 ),
        ( 0x3D0F08ED, 0xF32E3FDE, 0xBB8A1A8C, 0xC3A3FEC4 ),
        ( 0x2EC171F8, 0x33698309, 0x78EFD172, 0xD764B98C ),
        ( 0x5CECEEAC, 0xA174084C, 0x95C3A400, 0x98BEE220 ),
        ( 0xBBDD0C2D, 0xFAB6FCD9, 0xDCCC080E, 0x9F04B41F ),
        ( 0x60B3F7AF, 0x37EEE7C8, 0x836CFD98, 0x782CA060 ),
        ( 0xDF44EA33, 0xB0B2C398, 0x0583CE6F, 0x846D823E ),
        ( 0xC7E31175, 0x6DB4E34D, 0xDAD60CA1, 0xE95ABA60 ),
        ( 0xE0DC6938, 0x84A0A7E3, 0xB7F695B5, 0xB46A010B ),
        ( 0x1CEB6C66, 0x3535F274, 0x839DBC27, 0x80B4599C ),
        ( 0xBBA106F4, 0xD49B697C, 0xB454B5D9, 0x2B69E58B ),
        ( 0x5AD58A39, 0xDFD52844, 0x34973366, 0x8F467DDC ),
        ( 0x67A67B1F, 0x3575ECB3, 0x1C71B19D, 0xA885C92B ),
        ( 0xD5ABCC27, 0x9114EFF5, 0xA094340E, 0xA457374B ),
        ( 0xB559DF49, 0xDEC9B2CF, 0x0F97FE2B, 0x5FA054D7 ),
        ( 0x2ACA7229, 0x99FF1B77, 0x156D66E0, 0xF7A55486 ),
        ( 0x565996FD, 0x8F988CEF, 0x27DC2CE2, 0x2F8AE186 ),
        ( 0xBE473747, 0x2590827B, 0xDC852399, 0x2DE46519 ),
        ( 0xF860AB7D, 0x00F48C88, 0x0ABFBB33, 0x91EA1838 ),
        ( 0xDE15C7E1, 0x1D90EFF8, 0xABC70129, 0xD9B2F0B4 ),
        ( 0xB3F0A2C3, 0x775539A7, 0x6CAA3BC1, 0xD5A6FC7E ),
        ( 0x127C6E21, 0x6C07A459, 0xAD851388, 0x22E8BF5B ),
        ( 0x08F3F132, 0x57B587E3, 0x087AD505, 0xFA070C27 ),
        ( 0xA826E824, 0x3F851E6A, 0x9D1F2276, 0x7962AD37 ),
        ( 0x14A6A13A, 0x469962FD, 0x914DB278, 0x3A9E8EC2 ),
        ( 0xFE20DDF7, 0x06505229, 0xF9C9F394, 0x4361A98D ),
        ( 0x1DE7A33C, 0x37F81C96, 0xD9B967BE, 0xC00FA4FA ),
        ( 0x5FD01E9A, 0x9F2E486D, 0x93205409, 0x814D7CC2 ),
        ( 0xE17F5CA5, 0x37D4BDD0, 0x1F408335, 0x43B6B603 ),
        ( 0x817CEEAE, 0x796C9EC0, 0x1BB3DED7, 0xBAC7263B ),
        ( 0xB7827E63, 0x0988FEA0, 0x3800BD91, 0xCF876B00 ),
        ( 0xF0248D4B, 0xACA7BDC8, 0x739E30F3, 0xE0C469C2 ),
        ( 0x67363EB6, 0xFAE8E047, 0xF0C1C8E5, 0x828CCD47 ),
        ( 0x3DBD1D15, 0x05092D7B, 0x216FC6E3, 0x446860FB ),
        ( 0xEBF39102, 0x8F4C1708, 0x519D2F36, 0xC67C5437 ),
        ( 0x89A0D454, 0x9201A282, 0xEA1B1E50, 0x1771BEDC ),
        ( 0x9047FAD7, 0x88136D8C, 0xA488286B, 0x7FE9352C )
        ]]
    k = b'\x33\x34\x3D\x83\x9F\x38\x9F\x00\x4F\xE6\x98\x23\x39\xCF\x7A\x41'
    tlen = 8
    msg = ''.join(chr(i) for i in range(64)).encode('utf-8')
    for i in range(64):
        assert chaskey(k,tlen,msg[:i]).hexdigest() == vectors[i][32-2*tlen:32], \
            ('failed on test no %i' % i)

    # fixed doctests; cf. Marek Majkowski
    import doctest
    EVAL_FLAG = doctest.register_optionflag("EVAL")
    OrigOutputChecker = doctest.OutputChecker

    def relaxed_eval(s):
        if s.strip():
            return eval(s)
        else:
            return None

    class MyOutputChecker:
        def __init__(self):
            self.orig = OrigOutputChecker()

        def check_output(self, want, got, optionflags):
            if optionflags & EVAL_FLAG:
                return relaxed_eval(got) == relaxed_eval(want)
            else:
                return self.orig.check_output(want, got, optionflags)

        def output_difference(self, example, got, optionflags):
            return self.orig.output_difference(example, got, optionflags)

    doctest.OutputChecker = MyOutputChecker

    if doctest.testmod(optionflags=EVAL_FLAG)[0] == 0: print("all tests ok")
'''