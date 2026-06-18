# Serial port defaults
DEFAULT_METTLER_PORT = "COM8"
DEFAULT_METTLER_BAUD = 9600

DEFAULT_IDA_PORT = "COM11"
DEFAULT_IDA_BAUD = 115200

# IDA5 session defaults
DEFAULT_IDA_CH = 1
DEFAULT_PARAM_A = "1"
DEFAULT_PARAM_B = "kaew"
DEFAULT_PARAM_C = "100"

# Timing
POLL_IDA_SEC = 0.1              # IDA5 query interval (was 0.5 s — now 100 ms for ~5 Hz)
UI_REFRESH_MS = 100             # Tkinter UI tick (was 250 ms — now 100 ms)
MAX_POINTS = 3600               # ring-buffer depth per source (~1 h at 1 Hz)
TABLE_ROWS = 35

METTLER_POLL_SLEEP = 0.002      # in_waiting poll interval for Mettler reader (2 ms)
IDA_RESPONSE_TIMEOUT = 0.5     # readline() timeout for IDA5 command/response
