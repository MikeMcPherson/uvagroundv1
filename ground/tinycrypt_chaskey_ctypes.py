import ctypes

chaskey_lib = ctypes.CDLL('ground/chaskey.so')
chaskey_lib.chas_encrypt.argtypes = (ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)
chaskey_lib.chas_mac.argtypes = (ctypes.c_ushort, ctypes.c_ushort, ctypes.c_ulong, ctypes.c_ushort)


def chas_encrypt(enc_mode, key, buf):
    global chaskey_lib
    num_numbers = len(numbers)
    array_type = ctypes.c_int * num_numbers
    result = chaskey_lib.our_function(ctypes.c_int(num_numbers), array_type(*numbers))
    return int(result)


def chas_mac(digest, msg, msglen, key):
    global chaskey_lib
    num_numbers = len(numbers)
    array_type = ctypes.c_int * num_numbers
    result = chaskey_lib.our_function(ctypes.c_int(num_numbers), array_type(*numbers))
    return int(result)
