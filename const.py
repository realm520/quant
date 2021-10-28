from enum import IntEnum


class PositionStatus(IntEnum):
    PREPARE_OPEN = 1    # before send open order
    ORDER_OPEN = 2      # open order sent
    FILL_OPEN = 3       # open order filled
    ORDER_CLOSE = 4     # close order sent
    FILL_CLOSE = 5      # close order filled (final status)
