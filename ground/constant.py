COMMAND_NAMES = {
    0x05: 'ACK',
    0x06: 'NAK',
    0x7F: 'CEASE_XMIT',
    0x09: 'NOOP',
    0x04: 'RESET',
    0x01: 'XMIT_COUNT',
    0x02: 'XMIT_HEALTH',
    0x03: 'XMIT_SCIENCE',
    0x08: 'READ_MEM',
    0x07: 'WRITE_MEM',
    0x0B: 'SET_COMMS',
    0x0C: 'GET_COMMS',
    0x0A: 'SET_MODE',
    0x0E: 'MAC_TEST',
    0x31: 'PING_RETURN',
    0x33: 'RADIO_RESET',
    0x34: 'PIN_TOGGLE'
}
COMMAND_CODES = {}
for code, cmd in COMMAND_NAMES.items():
    COMMAND_CODES.update({cmd: code})
